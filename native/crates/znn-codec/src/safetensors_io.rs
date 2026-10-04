//! safetensors container I/O — mmap reads, an order-preserving canonical
//! writer and atomic replacement.
//!
//! # Format facts (primary sources, re-verified 2026-09-24)
//!
//! Container: `[u64 LE header_len][header JSON region][dense tensor data]`.
//! The reference implementation is the Rust `safetensors` crate v0.8.0
//! (`safetensors/src/tensor.rs`), whose semantics this module mirrors exactly:
//!
//! * **writer** (`prepare()` + `Serialize for Metadata`): `__metadata__` (a
//!   string→string map) is emitted FIRST when present, then one entry per
//!   tensor — `{"dtype":"…","shape":[…],"data_offsets":[a,b]}` in struct
//!   field order, compact serde_json (no insignificant whitespace, raw UTF-8,
//!   minimal escaping) — with tensors in the order the caller sorted them
//!   (torch's `save_file` sorts by descending dtype alignment, then name),
//!   densely packed offsets, and the JSON region **space-padded to a
//!   multiple of 8 bytes** (`metadata_buf.resize(next_multiple_of(8), b' ')`).
//! * **reader** (`SafeTensors::read_metadata` + `Metadata::validate`):
//!   header region ≤ 100 MB, JSON must deserialize, tensor entries must be
//!   DENSE (`s != start → InvalidOffset`), sizes must equal
//!   `shape.product() * dtype.bitsize() / 8` (with `nbits % 8 == 0`), and the
//!   data region must be covered EXACTLY (`MetadataIncompleteBuffer`).
//!   The JSON key order is arbitrary for readers (entries are indexed by
//!   name and sorted by offset internally).
//!
//! # Why Neo writes its own header
//!
//! The reference `serialize` re-sorts tensors and re-randomises metadata key
//! order (its metadata map is a `HashMap`), so a torch-mediated round trip
//! only restores the original bytes by luck. Neo's writer instead **preserves
//! the source file's JSON key order and metadata order** and reproduces the
//! canonical byte format, which makes decompression **byte-exact** for every
//! file a standard tool wrote — and that guarantee is what turns
//! `znn_neo_src_sha256` into a real end-to-end check.
//! [`StContainer::canonical`] records whether a parsed file matches the
//! canonical form byte-for-byte; sources that do not (hand-edited headers,
//! exotic writers) still compress, but their restore is guaranteed at the
//! weaker "tensor data + metadata values equal" level and the
//! pipeline says so instead of failing the sha check blindly.
//!
//! All writes go through [`AtomicWriter`]: sibling `.tmp` → write → fsync →
//! rename → fsync(parent dir) (the legacy Python path has no
//! fsync at all). ENOSPC surfaces as [`StError::Io`] with the partial file
//! removed; nothing is ever renamed into place unverified.

use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use jiter::{Jiter, NumberInt, Peek};
use sha2::{Digest, Sha256};

use crate::CodecError;

/// Header-region size cap of the reference implementation
/// (`safetensors/src/tensor.rs MAX_HEADER_SIZE`) — hosts the 8 MB MoE
/// headers with a wide margin while keeping hostile u64 prefixes bounded.
pub const MAX_HEADER_SIZE: u64 = 100_000_000;

/// Length of the u64 header-size prefix.
pub const PREFIX_LEN: usize = 8;

/// Container-level errors: everything [`CodecError`] covers plus the I/O and
/// structural cases the safetensors layer adds.
#[derive(Debug, thiserror::Error)]
pub enum StError {
    #[error("safetensors format error: {0}")]
    Format(String),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Codec(#[from] CodecError),
    #[error("operation cancelled")]
    Cancelled,
    #[error("integrity verification failed: {0}")]
    Verification(String),
    /// A message that must reach the user VERBATIM (no prefix): the legacy
    /// error-wording compatibility contract — the UI displays these
    /// strings as-is and users search them, so they are contract, not prose
    /// (e.g. zipnn.py's delta length-mismatch ValueError).
    #[error("{0}")]
    Message(String),
}

/// Convenience alias for the safetensors/pipeline layer.
pub type StResult<T> = Result<T, StError>;

/// Bit width of every dtype string safetensors 0.8 defines — a verbatim port
/// of `Dtype::bitsize()` (`safetensors/src/tensor.rs`, read 2026-09-24).
/// Unknown dtype strings are rejected (the reference serde enum rejects them
/// too, so anything a standard tool can read, this can).
#[must_use]
pub fn dtype_bitsize(dtype: &str) -> Option<usize> {
    Some(match dtype {
        "F4" => 4,
        "F6_E2M3" | "F6_E3M2" => 6,
        "BOOL" | "U8" | "I8" | "F8_E5M2" | "F8_E4M3" | "F8_E8M0" | "F8_E4M3FNUZ"
        | "F8_E5M2FNUZ" => 8,
        "I16" | "U16" | "F16" | "BF16" => 16,
        "I32" | "U32" | "F32" => 32,
        "C64" | "F64" | "I64" | "U64" => 64,
        _ => return None,
    })
}

/// One tensor entry of the header, in JSON order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TensorEntry {
    /// Tensor name (the JSON key).
    pub name: String,
    /// dtype string exactly as written in the header (e.g. `"BF16"`).
    pub dtype: String,
    /// Shape dimensions as written (empty for scalars).
    pub shape: Vec<u64>,
    /// Byte range within the DATA region (dense per the reference validate).
    pub start: u64,
    /// Exclusive end within the data region.
    pub end: u64,
}

impl TensorEntry {
    /// Declared payload length (`end - start`).
    #[must_use]
    pub fn len(&self) -> u64 {
        self.end - self.start
    }

    /// True for zero-element payloads (`len() == 0`).
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.end == self.start
    }

    /// Number of elements (product of the shape; 1 for scalars — an empty
    /// product, exactly like the reference `try_fold(1, checked_mul)`).
    ///
    /// # Errors
    /// Overflowing products (hostile headers).
    pub fn nelem(&self) -> Result<u64, StError> {
        self.shape
            .iter()
            .try_fold(1u64, |acc, &d| acc.checked_mul(d))
            .ok_or_else(|| {
                StError::Format(format!("tensor {}: shape product overflows", self.name))
            })
    }
}

/// A parsed safetensors container header.
#[derive(Debug, Clone)]
pub struct StContainer {
    /// Value of the u64 prefix: length of the JSON region INCLUDING padding.
    pub header_region_len: u64,
    /// Absolute file offset where the tensor data region starts.
    pub data_start: usize,
    /// Tensor entries in JSON order (NOT offset order — they coincide for
    /// every standard-tool file and `canonical` says so).
    pub tensors: Vec<TensorEntry>,
    /// `__metadata__` entries in JSON order; `None` when the key is absent
    /// (the distinction matters: the reference writer omits `__metadata__`
    /// for None but emits `{}` for an empty map).
    pub metadata: Option<Vec<(String, String)>>,
    /// True when re-serialising this container canonically reproduces the
    /// original header bytes AND the JSON order equals the offset order —
    /// i.e. when Neo's writer can restore the source file byte-exactly.
    pub canonical: bool,
}

impl StContainer {
    /// Parse a whole file image (typically an mmap).
    ///
    /// # Errors
    /// Every structural violation the reference reader rejects (short file,
    /// oversized/invalid header, bad JSON, unknown dtype, misaligned or
    /// mismatched sizes, non-dense or uncovered data region), never a panic.
    pub fn parse(file: &[u8]) -> StResult<Self> {
        if file.len() < PREFIX_LEN {
            return Err(StError::Format(format!(
                "file is {} bytes — too short to be safetensors (need an 8-byte prefix)",
                file.len()
            )));
        }
        let region_len = u64::from_le_bytes(file[..PREFIX_LEN].try_into().expect("8 bytes"));
        if region_len > MAX_HEADER_SIZE {
            return Err(StError::Format(format!(
                "header size {region_len} exceeds the {MAX_HEADER_SIZE}-byte cap"
            )));
        }
        let region_len = usize::try_from(region_len)
            .map_err(|_| StError::Format("header size does not fit this platform".to_owned()))?;
        let data_start = PREFIX_LEN
            .checked_add(region_len)
            .ok_or_else(|| StError::Format("header size overflow".to_owned()))?;
        if data_start > file.len() {
            return Err(StError::Format(format!(
                "header declares {region_len} bytes but the file ends at {}",
                file.len() - PREFIX_LEN
            )));
        }
        let region = &file[PREFIX_LEN..data_start];
        // The canonical writer pads the JSON with trailing spaces; JSON
        // parsers accept trailing whitespace, and trimming keeps jiter's
        // finish() contract exact for hand-made headers with any whitespace.
        let json = trim_json_tail(region);
        let (tensors, metadata, dup_or_extra) = parse_header_json(json)?;

        let data_len = (file.len() - data_start) as u64;
        validate_entries(&tensors, data_len)?;

        // canonical ⇔ (a) JSON order == dense offset order (so a restore can
        // recompute the SAME offsets by walking the JSON order) and (b) the
        // canonical re-serialisation equals the original region bytes.
        let order_is_offset_order = tensors
            .iter()
            .scan(0u64, |expect_start, t| {
                let ok = t.start == *expect_start;
                *expect_start = t.end;
                Some(ok)
            })
            .all(|ok| ok);
        let rebuilt = build_header_region(
            metadata.as_deref(),
            &tensors
                .iter()
                .map(|t| OutEntry {
                    name: &t.name,
                    dtype: &t.dtype,
                    shape: &t.shape,
                    start: t.start,
                    end: t.end,
                })
                .collect::<Vec<_>>(),
        );
        let canonical = order_is_offset_order && !dup_or_extra && rebuilt == region;

        Ok(Self {
            header_region_len: region_len as u64,
            data_start,
            tensors,
            metadata,
            canonical,
        })
    }

    /// Parse from a file path via a read-only shared mmap (the
    /// model bytes never cross the Python boundary and are never copied —
    /// the OS page cache is the only buffer).
    ///
    /// # Errors
    /// Open/mmap failures or [`parse`](Self::parse) errors.
    // The crate's single, reviewed `unsafe` boundary (see the lib.rs lint
    // note): memmap2 declares `Mmap::map` unsafe because a concurrent
    // external WRITER mutating the file under a shared mapping is a data
    // race on the mapped bytes.
    #[allow(unsafe_code)]
    pub fn open(path: &Path) -> StResult<(Self, memmap2::Mmap)> {
        let file = File::open(path)?;
        let len = file.metadata()?.len();
        if len == 0 {
            // mmap of an empty file fails with EINVAL on Linux — reject
            // before mapping; an empty file is never valid safetensors.
            return Err(StError::Format("file is empty".to_owned()));
        }
        // SAFETY: read-only shared mapping (MAP_SHARED, PROT_READ) of a
        // model file that Neo's flows never mutate while mapped — the same
        // exposure the incumbent stack already takes (Python safetensors'
        // `safe_open` mmaps identically: shared read mappings
        // coexist with AV/indexer readers). A foreign writer racing the map
        // is outside the format contract; every CONSUMED byte still passes
        // the bounds/structure validation of `parse` and the codec's hostile
        // input checks, so the failure mode of a mutated file is a
        // verification error (sha mismatch), not UB in Neo's own logic.
        let mmap = unsafe { memmap2::Mmap::map(&file) }?;
        let container = Self::parse(&mmap)?;
        Ok((container, mmap))
    }

    /// The data slice of one entry (bounds-checked against the image).
    ///
    /// # Errors
    /// Offsets reaching past the file (truncated data region).
    pub fn data<'a>(&self, file: &'a [u8], entry: &TensorEntry) -> StResult<&'a [u8]> {
        let start = self
            .data_start
            .checked_add(usize::try_from(entry.start).map_err(|_| {
                StError::Format(format!(
                    "tensor {}: offset exceeds the address space",
                    entry.name
                ))
            })?)
            .ok_or_else(|| StError::Format("offset overflow".to_owned()))?;
        let end = start
            .checked_add(usize::try_from(entry.len()).map_err(|_| {
                StError::Format(format!(
                    "tensor {}: size exceeds the address space",
                    entry.name
                ))
            })?)
            .ok_or_else(|| StError::Format("size overflow".to_owned()))?;
        file.get(start..end).ok_or_else(|| {
            StError::Format(format!(
                "tensor {}: data region truncated ({}..{} beyond file size {})",
                entry.name,
                start,
                end,
                file.len()
            ))
        })
    }
}

pub(crate) fn trim_json_tail(region: &[u8]) -> &[u8] {
    let mut end = region.len();
    while end > 0 && matches!(region[end - 1], b' ' | b'\t' | b'\r' | b'\n') {
        end -= 1;
    }
    &region[..end]
}

/// jiter-driven header parse preserving JSON order. Returns
/// (tensors, metadata, saw-duplicate-or-extra-field).
type ParsedHeader = (Vec<TensorEntry>, Option<Vec<(String, String)>>, bool);

fn parse_header_json(json: &[u8]) -> StResult<ParsedHeader> {
    let mut j = Jiter::new(json);
    let mut tensors: Vec<TensorEntry> = Vec::new();
    // name → position in `tensors`, so the serde "last value wins" duplicate
    // rule is O(1) per tensor. A linear `tensors.iter().position(..)` scan per
    // key would be O(n²): a 64k-tensor MoE header then takes SECONDS to parse
    // (measured 6 s vs 0.33 s for the legacy json.loads path) — and both the
    // display route (`get_model_tensors`, K11) and the compress pipeline go
    // through here, so the map matters for correctness of the KPI, not just
    // cosmetics.
    let mut name_index: HashMap<String, usize> = HashMap::new();
    let mut metadata: Option<Vec<(String, String)>> = None;
    let mut odd = false; // duplicate keys / unknown fields (→ non-canonical)
    let mut seen_meta = false;

    // jiter ties the returned &str lifetimes to the &mut borrow, so keys
    // are owned immediately — the parser state must be free for the value
    // calls inside the loop body.
    let mut key: Option<String> = j.next_object().map_err(json_err)?.map(str::to_owned);
    if key.is_none() {
        // `{}` — a header with no tensors at all is structurally valid
        j.finish().map_err(json_err)?;
        return Ok((tensors, None, false));
    }
    while let Some(k) = key.take() {
        if k == "__metadata__" {
            if seen_meta {
                odd = true; // duplicate __metadata__
            }
            seen_meta = true;
            metadata = Some(parse_metadata_map(&mut j, &mut odd)?);
        } else {
            let entry = parse_tensor_entry(&mut j, &k, &mut odd)?;
            // duplicate-name semantics of serde: the LAST value wins (replace
            // in place, so the JSON order of first appearance is preserved).
            match name_index.get(&k) {
                Some(&pos) => {
                    odd = true; // duplicate tensor name
                    tensors[pos] = entry;
                }
                None => {
                    name_index.insert(k.clone(), tensors.len());
                    tensors.push(entry);
                }
            }
        }
        key = j.next_key().map_err(json_err)?.map(str::to_owned);
    }
    j.finish().map_err(json_err)?;
    Ok((tensors, metadata, odd))
}

fn json_err(e: jiter::JiterError) -> StError {
    StError::Format(format!("invalid header JSON: {e}"))
}

fn parse_metadata_map(j: &mut Jiter, odd: &mut bool) -> StResult<Vec<(String, String)>> {
    let mut out = Vec::new();
    let mut key: Option<String> = j.next_object().map_err(json_err)?.map(str::to_owned);
    while let Some(k) = key.take() {
        let v = j.next_str().map_err(|e| {
            StError::Format(format!(
                "__metadata__ value for key {k:?} is not a string ({e}) — the reference reader rejects this"
            ))
        })?;
        let v = v.to_owned();
        if out.iter().any(|(ek, _)| *ek == k) {
            *odd = true;
        }
        out.push((k, v));
        key = j.next_key().map_err(json_err)?.map(str::to_owned);
    }
    Ok(out)
}

fn parse_tensor_entry(j: &mut Jiter, name: &str, odd: &mut bool) -> StResult<TensorEntry> {
    let mut dtype: Option<String> = None;
    let mut shape: Option<Vec<u64>> = None;
    let mut offsets: Option<(u64, u64)> = None;
    let mut key: Option<String> = match j.next_object().map_err(json_err)?.map(str::to_owned) {
        Some(k) => Some(k),
        None => {
            return Err(StError::Format(format!(
                "tensor {name:?}: entry is an empty object (dtype/shape/data_offsets required)"
            )));
        }
    };
    while let Some(k) = key.take() {
        match k.as_str() {
            "dtype" => {
                let s = j.next_str().map_err(json_err)?;
                dtype = Some(s.to_owned());
            }
            "shape" => shape = Some(parse_int_array(j, name, &k)?),
            "data_offsets" => {
                let vals = parse_int_array(j, name, &k)?;
                if vals.len() != 2 {
                    return Err(StError::Format(format!(
                        "tensor {name:?}: data_offsets must hold exactly 2 integers, got {}",
                        vals.len()
                    )));
                }
                offsets = Some((vals[0], vals[1]));
            }
            _ => {
                // The reference TensorInfo ignores unknown fields (serde
                // default) — tolerate, but the entry can no longer be
                // re-serialised byte-identically.
                *odd = true;
                j.next_skip().map_err(json_err)?;
            }
        }
        key = j.next_key().map_err(json_err)?.map(str::to_owned);
    }
    let dtype = dtype.ok_or_else(|| StError::Format(format!("tensor {name:?}: missing dtype")))?;
    let shape = shape.ok_or_else(|| StError::Format(format!("tensor {name:?}: missing shape")))?;
    let (start, end) =
        offsets.ok_or_else(|| StError::Format(format!("tensor {name:?}: missing data_offsets")))?;
    if end < start {
        return Err(StError::Format(format!(
            "tensor {name:?}: data_offsets [{start}, {end}] are inverted"
        )));
    }
    Ok(TensorEntry {
        name: name.to_owned(),
        dtype,
        shape,
        start,
        end,
    })
}

fn parse_int_array(j: &mut Jiter, name: &str, field: &str) -> StResult<Vec<u64>> {
    let mut out = Vec::new();
    let mut peek = match j.next_array().map_err(json_err)? {
        Some(p) => Some(p),
        None => return Ok(out),
    };
    while let Some(p) = peek {
        if p == Peek::Null {
            // serde rejects null inside Vec<usize> — mirror that
            return Err(StError::Format(format!(
                "tensor {name:?}: null inside {field}"
            )));
        }
        match j.next_int().map_err(json_err)? {
            NumberInt::Int(v) if v >= 0 => out.push(v as u64),
            NumberInt::Int(v) => {
                return Err(StError::Format(format!(
                    "tensor {name:?}: negative value {v} in {field}"
                )));
            }
            NumberInt::BigInt(_) => {
                return Err(StError::Format(format!(
                    "tensor {name:?}: value in {field} exceeds u64"
                )));
            }
        }
        peek = j.array_step().map_err(json_err)?;
    }
    Ok(out)
}

/// The reference validation pass (`Metadata::validate` + the buffer-coverage
/// check of `read_metadata`): dtype known, `nbits % 8 == 0`, declared size
/// equals `shape × dtype`, and the entries tile the data region densely
/// (sorted by offset — JSON order may legitimately differ).
fn validate_entries(tensors: &[TensorEntry], data_len: u64) -> StResult<()> {
    let mut order: Vec<&TensorEntry> = tensors.iter().collect();
    order.sort_by_key(|t| t.start);
    let mut expect_start = 0u64;
    for t in order {
        let bits = dtype_bitsize(&t.dtype).ok_or_else(|| {
            StError::Format(format!(
                "tensor {}: unknown dtype {:?} (safetensors 0.8 defines 22; the reference reader rejects unknown dtypes)",
                t.name, t.dtype
            ))
        })?;
        let nelem = t.nelem()?;
        let nbits = nelem
            .checked_mul(bits as u64)
            .ok_or_else(|| StError::Format(format!("tensor {}: size overflow", t.name)))?;
        if nbits % 8 != 0 {
            return Err(StError::Format(format!(
                "tensor {}: {bits}-bit dtype with {nelem} elements does not end on a byte boundary",
                t.name
            )));
        }
        let size = nbits / 8;
        if t.len() != size {
            return Err(StError::Format(format!(
                "tensor {}: data_offsets span {} bytes but shape {shape:?} × {dtype} needs {size}",
                t.name,
                t.len(),
                shape = t.shape,
                dtype = t.dtype
            )));
        }
        if t.start != expect_start {
            return Err(StError::Format(format!(
                "tensor {}: data_offsets start at {} but the previous tensor ends at {expect_start} (the format is dense — gaps/overlaps are invalid)",
                t.name, t.start
            )));
        }
        expect_start = t.end;
    }
    if expect_start != data_len {
        return Err(StError::Format(format!(
            "tensor data covers {expect_start} bytes but the file's data region is {data_len} (the region must be covered exactly)"
        )));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Canonical writer (byte-identical to safetensors-rust `prepare()` output)
// ---------------------------------------------------------------------------

/// One tensor entry to serialise (offsets are explicit so the same builder
/// serves the canonical-form check, the worst-case bound and the real write).
#[derive(Debug, Clone, Copy)]
pub struct OutEntry<'a> {
    /// Tensor name.
    pub name: &'a str,
    /// dtype string (`"U8"`, `"BF16"`, …).
    pub dtype: &'a str,
    /// Shape dimensions.
    pub shape: &'a [u64],
    /// Data-region start offset.
    pub start: u64,
    /// Data-region end offset.
    pub end: u64,
}

/// Build the FULL header region (JSON + space padding to a multiple of 8)
/// exactly like safetensors-rust does: `{"__metadata__":{…},…tensors…}` in
/// compact serde_json form, `__metadata__` first when present.
#[must_use]
pub fn build_header_region(metadata: Option<&[(String, String)]>, tensors: &[OutEntry]) -> Vec<u8> {
    let mut out = Vec::with_capacity(96 + tensors.len() * 96);
    out.push(b'{');
    let mut first = true;
    if let Some(entries) = metadata {
        out.extend_from_slice(b"\"__metadata__\":{");
        for (i, (k, v)) in entries.iter().enumerate() {
            if i > 0 {
                out.push(b',');
            }
            write_json_string(&mut out, k);
            out.push(b':');
            write_json_string(&mut out, v);
        }
        out.push(b'}');
        first = false;
    }
    for t in tensors {
        if !first {
            out.push(b',');
        }
        first = false;
        write_json_string(&mut out, t.name);
        out.extend_from_slice(b":{\"dtype\":");
        write_json_string(&mut out, t.dtype);
        out.extend_from_slice(b",\"shape\":[");
        for (i, d) in t.shape.iter().enumerate() {
            if i > 0 {
                out.push(b',');
            }
            out.extend_from_slice(d.to_string().as_bytes());
        }
        out.extend_from_slice(b"],\"data_offsets\":[");
        out.extend_from_slice(t.start.to_string().as_bytes());
        out.push(b',');
        out.extend_from_slice(t.end.to_string().as_bytes());
        out.extend_from_slice(b"]}");
    }
    out.push(b'}');
    // "Force alignment to 8 bytes." — safetensors-rust prepare()
    let aligned = out.len().next_multiple_of(PREFIX_LEN);
    out.resize(aligned, b' ');
    out
}

/// serde_json's minimal string escaping (what the reference writer uses):
/// `"` `\` and C0 controls escaped, `\b \t \n \f \r` short forms, everything
/// else — including all non-ASCII — raw UTF-8.
fn write_json_string(out: &mut Vec<u8>, s: &str) {
    out.push(b'"');
    for b in s.as_bytes() {
        match b {
            b'"' => out.extend_from_slice(b"\\\""),
            b'\\' => out.extend_from_slice(b"\\\\"),
            0x08 => out.extend_from_slice(b"\\b"),
            0x09 => out.extend_from_slice(b"\\t"),
            0x0A => out.extend_from_slice(b"\\n"),
            0x0C => out.extend_from_slice(b"\\f"),
            0x0D => out.extend_from_slice(b"\\r"),
            c if *c < 0x20 => {
                out.extend_from_slice(b"\\u00");
                out.push(HEX[(c >> 4) as usize]);
                out.push(HEX[(c & 0xF) as usize]);
            }
            c => out.push(*c),
        }
    }
    out.push(b'"');
}

const HEX: [u8; 16] = *b"0123456789abcdef";

/// Python `json.dumps(…, ensure_ascii=True)` string escaping — the form the
/// legacy pipeline's `znn_compressed_vectors` value uses (`json.dumps` of the
/// infos dict). Non-ASCII becomes `\uXXXX` (lowercase hex, surrogate pairs
/// above the BMP), so a Neo-native compressed file records the metadata
/// value byte-identically to the legacy path.
#[must_use]
pub fn py_escape_json_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{08}' => out.push_str("\\b"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\u{0C}' => out.push_str("\\f"),
            '\r' => out.push_str("\\r"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c if (c as u32) < 0x80 => out.push(c),
            c if (c as u32) <= 0xFFFF => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => {
                // surrogate pair (Python json.dumps ensure_ascii semantics)
                let v = c as u32 - 0x1_0000;
                let hi = 0xD800 + (v >> 10);
                let lo = 0xDC00 + (v & 0x3FF);
                out.push_str(&format!("\\u{hi:04x}\\u{lo:04x}"));
            }
        }
    }
    out.push('"');
    out
}

/// Render the `znn_compressed_vectors` metadata value EXACTLY like the
/// legacy pipeline does: `json.dumps({name: {"dtype": d, "shape": s}, …})`
/// with Python's default separators (`", "` / `": "`) and `ensure_ascii`
/// escaping, entries in ascending name order (the legacy path iterates
/// `safe_open(...).keys()`, which the safetensors binding sorts).
#[must_use]
pub fn py_dumps_compressed_vectors(infos: &[(String, String, String)]) -> String {
    let mut out = String::from("{");
    for (i, (name, dtype, shape)) in infos.iter().enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        out.push_str(&py_escape_json_string(name));
        out.push_str(": {\"dtype\": ");
        out.push_str(&py_escape_json_string(dtype));
        out.push_str(", \"shape\": ");
        out.push_str(&py_escape_json_string(shape));
        out.push('}');
    }
    out.push('}');
    out
}

/// Read the leading header JSON region of a safetensors file (no data-region
/// validation, no full-file mmap — a display read must succeed on a file whose
/// tensor data is truncated as long as its header is intact, exactly like the
/// incumbent `comfy.utils.safetensors_header`).
///
/// Shared by [`header_display_json`] and [`tensor_tree_json`] so both display
/// paths enforce the same B4 cap and see the same bytes (and therefore the same
/// tensor order — the tree's leaf indices address that order).
///
/// # Errors
/// Open/read failures, an oversized header (`max_header`, the B4 unified
/// 32 MiB cap) or a file truncated before the end of its header.
fn read_header_region(path: &Path, max_header: u64) -> StResult<Vec<u8>> {
    use std::io::Read;
    let mut f = File::open(path).map_err(|e| crate::pipeline::io_ctx(e, "reading", path))?;
    let mut prefix = [0u8; PREFIX_LEN];
    f.read_exact(&mut prefix).map_err(|_| {
        StError::Format("file is too short to hold a safetensors header".to_owned())
    })?;
    let header_len = u64::from_le_bytes(prefix);
    if header_len > max_header {
        return Err(StError::Format(format!(
            "header size {header_len} exceeds the {max_header}-byte cap"
        )));
    }
    let len = usize::try_from(header_len)
        .map_err(|_| StError::Format("header size does not fit this platform".to_owned()))?;
    let mut region = vec![0u8; len];
    f.read_exact(&mut region).map_err(|_| {
        StError::Format("file is truncated before the end of its header".to_owned())
    })?;
    Ok(region)
}

/// Version of the tensor-tree wire format emitted by [`tensor_tree_json`].
pub const TENSOR_TREE_VERSION: u32 = 1;

/// The name of a folder level that is empty (`a..b` → the middle level), as the
/// frontend's grouping has always rendered it.
const UNNAMED_SEGMENT: &str = "(unnamed)";

/// One node of the tree while it is being built (index-addressed: a node's
/// parent always has a SMALLER index than the node itself, because a parent is
/// created while walking the path of the tensor that first mentions it — which
/// makes the bottom-up aggregate pass a single reverse iteration).
struct TreeBuildNode {
    segment: String,
    children: Vec<u32>,
    /// Indices into the header's `tensors` list, in header order.
    leaves: Vec<u32>,
    /// `u32::MAX` for the root.
    parent: u32,
    /// Subtree tensor count (aggregate).
    count: u64,
    /// Subtree parameter count (aggregate; saturating — see `tensor_params`).
    params: u64,
}

/// `shape.reduce((acc, dim) => acc * dim, 1)` — the frontend's parameter count
/// of one tensor (a scalar shape counts as 1). Saturating: a hostile header
/// could describe a tensor whose element count exceeds `u64`, and a debug
/// overflow panic (or a silent release wrap) is not an acceptable answer for a
/// display aggregate.
fn tensor_params(shape: &[u64]) -> u64 {
    shape.iter().fold(1u64, |acc, dim| acc.saturating_mul(*dim))
}

/// Fold a parsed header's tensor list into the display tree and encode it
/// ("テンソルツリー事前グループ化", Phase 6).
///
/// Grouping rule — identical to the frontend's historical `tensorTree`
/// computed, which this replaces for the expensive part: a tensor name is split
/// on `.`; every segment but the last is a folder level (an empty segment reads
/// `(unnamed)`), the last segment is the leaf, and a name without a dot is a
/// leaf of the root. Folders are created on first appearance, so children and
/// leaves come out in HEADER order; the *display* order stays the frontend's
/// `naturalCompare`, which it now applies only to the nodes it actually renders
/// (a collapsed MoE tree renders ~2 of its 87k nodes).
pub fn encode_tensor_tree(tensors: &[TensorEntry]) -> String {
    // ---- build (index-addressed, parent index < child index) ---------------
    let mut nodes: Vec<TreeBuildNode> = Vec::with_capacity(tensors.len() / 4 + 1);
    nodes.push(TreeBuildNode {
        segment: String::new(),
        children: Vec::new(),
        leaves: Vec::new(),
        parent: u32::MAX,
        count: 0,
        params: 0,
    });
    // dotted folder path → node index
    let mut by_path: HashMap<String, u32> = HashMap::new();

    for (ti, tensor) in tensors.iter().enumerate() {
        let Some(ti32) = u32::try_from(ti).ok() else {
            break; // >4 G entries: unreachable under the 32 MiB header cap
        };
        let segments: Vec<&str> = tensor.name.split('.').collect();
        let folders = segments.len().saturating_sub(1);
        let mut parent: u32 = 0;
        let mut path = String::new();
        for segment in &segments[..folders] {
            let name = if segment.is_empty() {
                UNNAMED_SEGMENT
            } else {
                segment
            };
            if !path.is_empty() {
                path.push('.');
            }
            path.push_str(name);
            parent = match by_path.get(&path) {
                Some(&idx) => idx,
                None => {
                    let idx = u32::try_from(nodes.len()).unwrap_or(u32::MAX);
                    if idx == u32::MAX {
                        break; // index space exhausted (unreachable, see above)
                    }
                    nodes.push(TreeBuildNode {
                        segment: name.to_owned(),
                        children: Vec::new(),
                        leaves: Vec::new(),
                        parent,
                        count: 0,
                        params: 0,
                    });
                    let parent_idx = parent as usize;
                    nodes[parent_idx].children.push(idx);
                    by_path.insert(path.clone(), idx);
                    idx
                }
            };
        }
        let parent_idx = parent as usize;
        nodes[parent_idx].leaves.push(ti32);
        nodes[parent_idx].count = nodes[parent_idx].count.saturating_add(1);
        nodes[parent_idx].params = nodes[parent_idx]
            .params
            .saturating_add(tensor_params(&tensor.shape));
    }

    // ---- aggregates (children always have a greater index) ----------------
    for idx in (1..nodes.len()).rev() {
        let parent = nodes[idx].parent as usize;
        let count = nodes[idx].count;
        let params = nodes[idx].params;
        nodes[parent].count = nodes[parent].count.saturating_add(count);
        nodes[parent].params = nodes[parent].params.saturating_add(params);
    }

    // ---- emit: pre-order, own leaves before children ----------------------
    // (the layout the frontend decodes with one running cursor — no offsets on
    // the wire, no recursion here either: an iterative frame stack keeps a
    // pathologically deep name from overflowing the native stack.)
    let mut out = String::with_capacity(nodes.len() * 24 + tensors.len() * 6 + 32);
    out.push_str("{\"v\":");
    out.push_str(&TENSOR_TREE_VERSION.to_string());
    out.push_str(",\"nodes\":[");
    let mut leaves_out = String::with_capacity(tensors.len() * 6 + 2);
    leaves_out.push('[');
    let mut leaf_count = 0usize;

    #[derive(Clone, Copy)]
    struct Frame {
        node: usize,
        next: usize,
    }
    let mut stack: Vec<Frame> = vec![Frame { node: 0, next: 0 }];
    let mut emitted = 0usize;
    while let Some(&Frame { node, next }) = stack.last() {
        if next == 0 {
            let build = &nodes[node];
            if emitted > 0 {
                out.push(',');
            }
            emitted += 1;
            out.push('[');
            out.push_str(&py_escape_json_string(&build.segment));
            out.push(',');
            out.push_str(&build.children.len().to_string());
            out.push(',');
            out.push_str(&build.leaves.len().to_string());
            out.push(',');
            out.push_str(&build.count.to_string());
            out.push(',');
            out.push_str(&build.params.to_string());
            out.push(']');
            for leaf in &build.leaves {
                if leaf_count > 0 {
                    leaves_out.push(',');
                }
                leaf_count += 1;
                leaves_out.push_str(&leaf.to_string());
            }
        }
        if next < nodes[node].children.len() {
            let child = nodes[node].children[next] as usize;
            if let Some(top) = stack.last_mut() {
                top.next = next + 1;
            }
            stack.push(Frame {
                node: child,
                next: 0,
            });
        } else {
            stack.pop();
        }
    }
    leaves_out.push(']');

    out.push_str("],\"leaves\":");
    out.push_str(&leaves_out);
    out.push('}');
    out
}

/// The display tensor tree of a safetensors file as JSON
/// (`{"v":1,"nodes":[[segment,childCount,tensorCount,totalCount,totalParams],…],
/// "leaves":[tensorIndex,…]}` — pre-order, root first; see
/// [`encode_tensor_tree`] for the grouping rule and `src/utils/tensorTree.ts`
/// for the decoder).
///
/// The leaf indices address the `tensors` array of [`header_display_json`] for
/// the SAME file (both come from one [`parse_header_json`] order), so the
/// frontend never re-transfers the tensor entries.
///
/// # Errors
/// The same failures as [`header_display_json`] (open/read, the B4 cap,
/// a truncated or invalid header).
pub fn tensor_tree_json(path: &Path, max_header: u64) -> StResult<String> {
    let region = read_header_region(path, max_header)?;
    let json = trim_json_tail(&region);
    let (tensors, _metadata, _odd) = parse_header_json(json)?;
    Ok(encode_tensor_tree(&tensors))
}

/// Header-only parse for the model-detail display functions
/// (`py/utils.py get_model_metadata` / `get_model_tensors`).
///
/// Reads just the leading JSON region (no data-region validation, no full-file
/// mmap — a display read must succeed on a file whose tensor data is truncated
/// as long as its header is intact, exactly like the incumbent
/// `comfy.utils.safetensors_header` + `json.loads`), parses it with jiter (the
/// K11 fast path), and returns the DIGESTED shape the two Python functions
/// need as one JSON document:
///
/// ```json
/// {"metadata": {…string→string, header order…},
///  "tensors": [{"name": …, "dtype": …, "shape": […]}, …]}
/// ```
///
/// `metadata` is `{}` when `__metadata__` is absent (Python's
/// `"__metadata__" not in dt → {}`); `tensors` preserves the header order and
/// omits `__metadata__` (Python's loop skips it). Strings are escaped with
/// [`py_escape_json_string`] so a `json.loads` on the Python side reproduces
/// the exact values the raw-header parse would. `max_header` is the B4 unified
/// cap (32 MiB) — an oversized header is an error the Python caller turns into
/// `{}`/`[]` (matching `safetensors_header(...) is None`).
///
/// # Errors
/// Open/read failures, an oversized or truncated header, or invalid header
/// JSON (all → the Python caller degrades to `{}`/`[]`).
pub fn header_display_json(path: &Path, max_header: u64) -> StResult<String> {
    let region = read_header_region(path, max_header)?;
    let json = trim_json_tail(&region);
    let (tensors, metadata, _odd) = parse_header_json(json)?;

    let mut out = String::from("{\"metadata\":{");
    if let Some(meta) = &metadata {
        for (i, (k, v)) in meta.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push_str(&py_escape_json_string(k));
            out.push(':');
            out.push_str(&py_escape_json_string(v));
        }
    }
    out.push_str("},\"tensors\":[");
    for (i, t) in tensors.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str("{\"name\":");
        out.push_str(&py_escape_json_string(&t.name));
        out.push_str(",\"dtype\":");
        out.push_str(&py_escape_json_string(&t.dtype));
        out.push_str(",\"shape\":[");
        for (j, d) in t.shape.iter().enumerate() {
            if j > 0 {
                out.push(',');
            }
            out.push_str(&d.to_string());
        }
        out.push_str("]}");
    }
    out.push_str("]}");
    Ok(out)
}

// ---------------------------------------------------------------------------
// Atomic writer
// ---------------------------------------------------------------------------

/// Sibling-tempfile atomic writer with optional inline SHA-256 (the
/// decompressor verifies WITHOUT re-reading the file — the
/// hasher consumes every byte exactly once on its way to disk).
///
/// Lifecycle: `new` creates `<dst>.tmp` (the legacy naming, so the startup
/// cleanup and the route-level failure cleanup recognise it) → `write_all`
/// streams → [`finish`](Self::finish) flushes + fsyncs (the file is durable
/// but still a tmp) → the caller VERIFIES → [`commit`](Self::commit) renames
/// into place + fsyncs the parent directory (the original is
/// only ever replaced after verification succeeded). Any error — or a plain
/// `drop` without `commit` (panic, process kill) — removes the partial file.
pub struct AtomicWriter {
    tmp: PathBuf,
    dst: PathBuf,
    inner: Option<BufWriter<File>>,
    hasher: Option<Sha256>,
    written: u64,
    committed: bool,
    dir_sync_error: Option<String>,
}

impl AtomicWriter {
    /// Create `<dst>.tmp` beside the destination (same filesystem ⇒ the
    /// rename is atomic) and start writing.
    ///
    /// Concurrency guard: the tmp is opened `create_new` — a SECOND live job
    /// for the same destination gets a clean error instead of both writers
    /// interleaving into one file (silent corruption). A tmp left behind by
    /// a crash is taken over once it is older than 15 minutes (the same
    /// staleness rule the startup sweep uses — a live run keeps rewriting
    /// its tmp, so a young one belongs to somebody).
    ///
    /// # Errors
    /// Open/create failures (including a read-only or full filesystem —
    /// the ENOSPC surfaces on the first write at the latest) and a young
    /// pre-existing `.tmp` (concurrent operation).
    pub fn new(dst: &Path, with_sha256: bool) -> StResult<Self> {
        let tmp = tmp_sibling(dst);
        let file = match OpenOptions::new().write(true).create_new(true).open(&tmp) {
            Ok(f) => f,
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                const STALE_AFTER_SECS: u64 = 900;
                let stale = std::fs::metadata(&tmp)
                    .and_then(|m| m.modified())
                    .map(|t| {
                        t.elapsed()
                            .map(|age| age.as_secs() >= STALE_AFTER_SECS)
                            .unwrap_or(true) // clock weirdness → treat as stale
                    })
                    .unwrap_or(true); // unstat-able → let the truncate open decide
                if !stale {
                    return Err(StError::Format(format!(
                        "{} exists and was modified less than {} minutes ago — another ZipNN operation for this target appears to be running (or one crashed moments ago); retry once it finishes or the startup cleanup has swept it",
                        tmp.display(),
                        STALE_AFTER_SECS / 60
                    )));
                }
                OpenOptions::new()
                    .write(true)
                    .create(true)
                    .truncate(true)
                    .open(&tmp)?
            }
            Err(e) => return Err(e.into()),
        };
        Ok(Self {
            tmp,
            dst: dst.to_path_buf(),
            inner: Some(BufWriter::with_capacity(1024 * 1024, file)),
            hasher: with_sha256.then(Sha256::new),
            written: 0,
            committed: false,
            dir_sync_error: None,
        })
    }

    /// The `.tmp` path being written (diagnostics/tests).
    #[must_use]
    pub fn tmp_path(&self) -> &Path {
        &self.tmp
    }

    /// Bytes written so far.
    #[must_use]
    pub fn written(&self) -> u64 {
        self.written
    }

    /// Stream bytes into the file (and the inline hasher when enabled).
    ///
    /// # Errors
    /// Any write failure — `std::io::ErrorKind::StorageFull` (ENOSPC) among
    /// them; the Drop guard removes the partial file.
    pub fn write_all(&mut self, bytes: &[u8]) -> StResult<()> {
        if let Some(h) = self.hasher.as_mut() {
            h.update(bytes);
        }
        let inner = self
            .inner
            .as_mut()
            .ok_or_else(|| StError::Format("writer already finished".to_owned()))?;
        inner.write_all(bytes)?;
        self.written += bytes.len() as u64;
        Ok(())
    }

    /// Overwrite already-written bytes at `offset` WITHOUT advancing the
    /// write position or feeding the hasher — the compressor's seek-back
    /// header patch (the payload was streamed at a worst-case offset; the
    /// exact header JSON is only known once every tensor is compressed).
    ///
    /// # Errors
    /// Seek/write failures.
    pub fn patch(&mut self, offset: u64, bytes: &[u8]) -> StResult<()> {
        use std::io::{Seek, SeekFrom};
        let inner = self
            .inner
            .as_mut()
            .ok_or_else(|| StError::Format("writer already finished".to_owned()))?;
        inner.flush()?;
        inner.seek(SeekFrom::Start(offset))?;
        inner.write_all(bytes)?;
        inner.flush()?;
        Ok(())
    }

    /// Flush → fsync(file). The durable content is still the `.tmp`; call
    /// [`commit`](Self::commit) only after verification succeeded. Returns
    /// the inline SHA-256 hex digest when hashing was enabled.
    ///
    /// # Errors
    /// Flush/fsync failures (ENOSPC typically bites at flush here — delayed
    /// allocation); the partial file is removed either way.
    pub fn finish(&mut self) -> StResult<Option<String>> {
        let digest = self.hasher.take().map(|h| hex(&h.finalize()));
        if let Some(mut inner) = self.inner.take() {
            inner.flush()?;
            inner.into_inner().map_err(|e| e.into_error())?.sync_all()?;
        }
        Ok(digest)
    }

    /// Rename the finished `.tmp` into place + fsync the parent directory
    /// (makes the replacement itself crash-durable).
    ///
    /// The RENAME is the commit point: once it succeeds the artifact is live
    /// and a failing directory fsync must not turn a complete, verified file
    /// into a reported job failure (that would leave "error + existing dst"
    /// — a confusing, retry-hostile state). The file CONTENT is already
    /// fsynced by [`finish`](Self::finish); without a durable dir entry the
    /// worst power-loss outcome is the rename not taking effect, i.e. the
    /// ORIGINAL staying intact — exactly the exposure the legacy path always
    /// had. The failure is surfaced as a warning instead
    /// ([`take_dir_sync_warning`]).
    ///
    /// # Errors
    /// Only a rename failure (or a commit before finish); the tmp is then
    /// removed by the Drop guard.
    pub fn commit(&mut self) -> StResult<()> {
        if self.inner.is_some() {
            return Err(StError::Format("commit before finish".to_owned()));
        }
        std::fs::rename(&self.tmp, &self.dst)?;
        self.committed = true;
        if let Err(e) = fsync_dir(self.dst.parent().unwrap_or_else(|| Path::new("."))) {
            self.dir_sync_error = Some(format!(
                "the parent-directory fsync after the rename failed ({e}) — the file is complete and content-fsynced, but the rename may not survive a power loss on this filesystem"
            ));
        }
        Ok(())
    }

    /// The non-fatal directory-fsync warning recorded by
    /// [`commit`](Self::commit) (call once after a successful commit).
    pub fn take_dir_sync_warning(&mut self) -> Option<String> {
        self.dir_sync_error.take()
    }

    /// Abort: remove the partial (or finished-but-uncommitted) file
    /// (by-reference so scoped error paths can abort and still return the
    /// error through the enclosing function).
    pub fn abort(&mut self) {
        self.inner = None;
        self.committed = true; // suppress the Drop guard
        let _ = std::fs::remove_file(&self.tmp);
    }

    /// Verification-failure path: preserve the finished tmp as
    /// a diagnostic artifact at `path` (the `.corrupt` retreat) instead of
    /// deleting it — the compressed source is NOT touched, so nothing is
    /// ever lost. An existing artifact at `path` is replaced.
    ///
    /// # Errors
    /// Rename failures (the Drop guard then removes the tmp as usual).
    pub fn reject_to(mut self, path: &Path) -> StResult<()> {
        self.inner = None;
        if path.exists() {
            std::fs::remove_file(path)?;
        }
        std::fs::rename(&self.tmp, path)?;
        self.committed = true; // the tmp now lives on AS `path`
        // best-effort dir durability (see commit() — the diagnostic file is
        // already content-fsynced by finish())
        let _ = fsync_dir(path.parent().unwrap_or_else(|| Path::new(".")));
        Ok(())
    }
}

impl Drop for AtomicWriter {
    fn drop(&mut self) {
        // A writer dropped WITHOUT commit() (error path, panic, kill, failed
        // verification) must never leave a stray `.tmp` behind.
        if !self.committed {
            self.inner = None;
            let _ = std::fs::remove_file(&self.tmp);
        }
    }
}

/// The `.tmp` sibling name — identical to the legacy Python pipeline's
/// (`f"{dst}.tmp"`) so route-level cleanup and the startup sweep catch
/// partials from BOTH paths.
#[must_use]
pub fn tmp_sibling(dst: &Path) -> PathBuf {
    let mut s = dst.as_os_str().to_os_string();
    s.push(".tmp");
    PathBuf::from(s)
}

/// fsync a directory (POSIX): makes the rename itself durable.
/// A no-op on platforms without directory fds (Windows).
pub fn fsync_dir(dir: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        let d = File::open(dir)?;
        d.sync_all()?;
    }
    #[cfg(not(unix))]
    {
        let _ = dir;
    }
    Ok(())
}

/// Lowercase hex of a digest.
#[must_use]
pub fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push(char::from(HEX[(b >> 4) as usize]));
        s.push(char::from(HEX[(b & 0xF) as usize]));
    }
    s
}

/// True for the ENOSPC family (write side) — the pipeline turns it into an
/// actionable "disk full" message with the partial output removed.
#[must_use]
pub fn is_enospc(e: &std::io::Error) -> bool {
    matches!(e.kind(), std::io::ErrorKind::StorageFull)
        || matches!(e.raw_os_error(), Some(28) | Some(49) | Some(112))
    // 28 = Linux ENOSPC, 49 = macOS EDQUOT-ish/ENOSPC variant, 112 = Windows
    // equivalent handled via ErrorKind; belt and braces across platforms.
}

/// SHA-256 of a byte image (the compressor hashes the mmap'd source on a
/// worker thread while the tensor loop runs).
pub fn sha256_chunks(
    data: &[u8],
    cancel: Option<&std::sync::atomic::AtomicBool>,
) -> Result<String, StError> {
    use std::sync::atomic::Ordering;
    let mut h = Sha256::new();
    const STEP: usize = 4 * 1024 * 1024;
    for chunk in data.chunks(STEP) {
        if cancel.is_some_and(|c| c.load(Ordering::Relaxed)) {
            return Err(StError::Cancelled);
        }
        h.update(chunk);
    }
    Ok(hex(&h.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry<'a>(
        name: &'a str,
        dtype: &'a str,
        shape: &'a [u64],
        start: u64,
        end: u64,
    ) -> OutEntry<'a> {
        OutEntry {
            name,
            dtype,
            shape,
            start,
            end,
        }
    }

    /// A minimal file image built by the canonical writer itself.
    fn file_image(
        metadata: Option<&[(String, String)]>,
        tensors: &[OutEntry],
        data: &[u8],
    ) -> Vec<u8> {
        let region = build_header_region(metadata, tensors);
        let mut out = Vec::new();
        out.extend_from_slice(&(region.len() as u64).to_le_bytes());
        out.extend_from_slice(&region);
        out.extend_from_slice(data);
        out
    }

    #[test]
    fn writer_matches_the_reference_format() {
        // Pinned byte-for-byte against a torch/safetensors-0.8.0 written
        // file (regenerated and diffed during the Phase-2 implementation
        // against `safetensors.torch.save_file` output — see tests/harness
        // cross-check on the Python side too).
        let meta = vec![("format".to_owned(), "pt".to_owned())];
        let tensors = vec![
            entry("b.weight", "BF16", &[2, 4], 0, 16),
            entry("a.weight", "F32", &[2], 16, 24),
        ];
        let region = build_header_region(Some(&meta), &tensors);
        let json = std::str::from_utf8(trim_json_tail(&region)).unwrap();
        assert_eq!(
            json,
            r#"{"__metadata__":{"format":"pt"},"b.weight":{"dtype":"BF16","shape":[2,4],"data_offsets":[0,16]},"a.weight":{"dtype":"F32","shape":[2],"data_offsets":[16,24]}}"#
        );
        assert_eq!(region.len() % 8, 0, "padded to 8");
        assert!(region[json.len()..].iter().all(|&b| b == b' '));
        // no metadata → no __metadata__ key at all
        let region2 = build_header_region(None, &tensors);
        let json2 = std::str::from_utf8(trim_json_tail(&region2)).unwrap();
        assert!(json2.starts_with(r#"{"b.weight""#));
        // empty metadata map → `"__metadata__":{}` (the reference writes
        // Some(empty map) exactly like this — and OMITS it for None)
        let region3 = build_header_region(Some(&[]), &tensors);
        let json3 = std::str::from_utf8(trim_json_tail(&region3)).unwrap();
        assert!(json3.starts_with(r#"{"__metadata__":{},"b.weight""#));
    }

    #[test]
    fn parse_roundtrip_and_canonical_flag() {
        let meta = vec![
            ("format".to_owned(), "pt".to_owned()),
            ("lang".to_owned(), "日本語".to_owned()),
        ];
        let tensors = vec![
            entry("s", "BF16", &[], 0, 2), // scalar
            entry("t", "F32", &[2, 2], 2, 18),
        ];
        let data = vec![7u8; 18];
        let img = file_image(Some(&meta), &tensors, &data);
        let st = StContainer::parse(&img).expect("parse");
        assert!(st.canonical, "writer output must parse as canonical");
        assert_eq!(st.tensors.len(), 2);
        assert_eq!(st.tensors[0].name, "s");
        assert_eq!(st.tensors[0].shape, Vec::<u64>::new());
        assert_eq!(st.metadata.as_ref().unwrap()[1].1, "日本語");
        assert_eq!(st.data_start, 8 + st.header_region_len as usize);
        assert_eq!(st.data(&img, &st.tensors[1]).unwrap(), &data[2..18]);
    }

    #[test]
    fn noncanonical_forms_are_detected_not_rejected() {
        let tensors = vec![entry("t", "F32", &[1], 0, 4)];
        let data = vec![0u8; 4];
        // (a) JSON order != offset order
        let two = vec![entry("z", "F32", &[1], 4, 8), entry("a", "F32", &[1], 0, 4)];
        let img = file_image(None, &two, &[0u8; 8]);
        let st = StContainer::parse(&img).expect("parse");
        assert!(!st.canonical, "offset order mismatch");
        // (b) padded with a non-multiple-of-8 header region
        let region = build_header_region(None, &tensors);
        let mut img = Vec::new();
        let trimmed = trim_json_tail(&region).to_vec();
        img.extend_from_slice(&(trimmed.len() as u64).to_le_bytes());
        img.extend_from_slice(&trimmed);
        img.extend_from_slice(&data);
        let st = StContainer::parse(&img).expect("parse unpadded");
        assert!(!st.canonical, "unpadded header");
        // (c) spaces after separators (json.dumps style)
        let loose = br#"{"t": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}"#;
        let mut img = Vec::new();
        let padded_len = loose.len().next_multiple_of(8);
        img.extend_from_slice(&(padded_len as u64).to_le_bytes());
        img.extend_from_slice(loose);
        img.resize(8 + padded_len, b' ');
        img.extend_from_slice(&data);
        let st = StContainer::parse(&img).expect("parse loose");
        assert!(!st.canonical, "extra whitespace");
        // (d) unknown extra field inside an entry
        let extra = br#"{"t":{"dtype":"F32","shape":[1],"data_offsets":[0,4],"min":[0]}}"#;
        let mut img = Vec::new();
        let padded_len = extra.len().next_multiple_of(8);
        img.extend_from_slice(&(padded_len as u64).to_le_bytes());
        img.extend_from_slice(extra);
        img.resize(8 + padded_len, b' ');
        img.extend_from_slice(&data);
        let st = StContainer::parse(&img).expect("parse extra field");
        assert!(!st.canonical, "extra field");
        assert_eq!(st.tensors[0].dtype, "F32");
        let _ = tensors;
    }

    #[test]
    fn hostile_containers_error_not_panic() {
        let bad: Vec<Vec<u8>> = vec![
            vec![],                                         // empty
            vec![0; 7],                                     // < prefix
            vec![255; 8],                                   // u64::MAX header len
            b"\x64\x00\x00\x00\x00\x00\x00\x00{}".to_vec(), // declares a 100-byte region, file ends after 2
            {
                // unknown dtype
                let region = br#"{"t":{"dtype":"QQQ","shape":[1],"data_offsets":[0,4]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v.extend_from_slice(&[0u8; 4]);
                v
            },
            {
                // size mismatch vs shape
                let region = br#"{"t":{"dtype":"F32","shape":[2],"data_offsets":[0,4]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v.extend_from_slice(&[0u8; 4]);
                v
            },
            {
                // gap between tensors
                let region = br#"{"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]},"b":{"dtype":"U8","shape":[1],"data_offsets":[2,3]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v.extend_from_slice(&[0u8; 3]);
                v
            },
            {
                // data region not covered exactly (trailing junk)
                let region = br#"{"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v.extend_from_slice(&[0u8; 5]);
                v
            },
            {
                // negative offset
                let region = br#"{"a":{"dtype":"U8","shape":[1],"data_offsets":[-1,0]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v
            },
            {
                // non-string metadata value
                let region = br#"{"__metadata__":{"a":5},"t":{"dtype":"U8","shape":[],"data_offsets":[0,0]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v
            },
            {
                // F4 sub-byte misalignment (3 nibbles = 12 bits)
                let region = br#"{"t":{"dtype":"F4","shape":[3],"data_offsets":[0,2]}}"#;
                let mut v = Vec::new();
                v.extend_from_slice(&(region.len() as u64).to_le_bytes());
                v.extend_from_slice(region);
                v.extend_from_slice(&[0u8; 2]);
                v
            },
        ];
        for img in bad {
            let r = StContainer::parse(&img);
            assert!(r.is_err(), "must reject: {img:?}");
        }
        // the empty-tensor header IS valid (region "{}", zero data)
        let mut v = Vec::new();
        v.extend_from_slice(&2u64.to_le_bytes());
        v.extend_from_slice(b"{}");
        let st = StContainer::parse(&v).expect("empty container parses");
        assert!(st.tensors.is_empty() && st.metadata.is_none());
    }

    #[test]
    fn atomic_writer_commits_and_aborts() {
        let dir = std::env::temp_dir().join(format!("mmneo-st-io-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let dst = dir.join("out.safetensors");

        // happy path: finish (durable tmp) → commit (rename)
        let mut w = AtomicWriter::new(&dst, true).unwrap();
        w.write_all(b"hello ").unwrap();
        w.write_all(b"world").unwrap();
        let sha = w.finish().unwrap().expect("sha enabled");
        assert_eq!(
            sha,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        );
        // finished but NOT committed: content is durable at the tmp path
        assert_eq!(std::fs::read(w.tmp_path()).unwrap(), b"hello world");
        assert!(!dst.exists());
        w.commit().unwrap();
        assert_eq!(std::fs::read(&dst).unwrap(), b"hello world");
        assert!(!tmp_sibling(&dst).exists(), "tmp consumed by rename");

        // abort path: the partial must vanish
        let mut w = AtomicWriter::new(&dst, false).unwrap();
        w.write_all(b"partial").unwrap();
        w.abort();
        assert!(!tmp_sibling(&dst).exists());
        assert_eq!(
            std::fs::read(&dst).unwrap(),
            b"hello world",
            "dst untouched"
        );

        // drop-without-commit path (finished but verification "failed")
        {
            let mut w = AtomicWriter::new(&dst, false).unwrap();
            w.write_all(b"dropped").unwrap();
            w.finish().unwrap();
        }
        assert!(!tmp_sibling(&dst).exists(), "Drop guard cleaned up");

        // concurrency guard: a second writer for the same dst is refused
        // while the first writer's tmp is young…
        let mut w1 = AtomicWriter::new(&dst, false).unwrap();
        w1.write_all(b"first job").unwrap();
        let err = match AtomicWriter::new(&dst, false) {
            Ok(_) => panic!("a second live writer for the same dst must be refused"),
            Err(e) => e.to_string(),
        };
        assert!(err.contains("another ZipNN operation"), "{err}");
        w1.abort();
        // …and a crash remnant is adopted once it is stale (backdated mtime)
        std::fs::write(tmp_sibling(&dst), b"crash remnant").unwrap();
        set_mtime_back(tmp_sibling(&dst), 3600);
        let mut w2 = AtomicWriter::new(&dst, false).unwrap();
        w2.write_all(b"second job").unwrap();
        w2.finish().unwrap();
        w2.commit().unwrap();
        assert_eq!(std::fs::read(&dst).unwrap(), b"second job");
        std::fs::remove_dir_all(&dir).ok();
    }

    /// Backdate a file's mtime (std `FileTimes`, stable since 1.75) to
    /// simulate a stale crash remnant.
    fn set_mtime_back(path: std::path::PathBuf, secs_ago: u64) {
        use std::fs::FileTimes;
        let when = std::time::SystemTime::now() - std::time::Duration::from_secs(secs_ago);
        let f = std::fs::OpenOptions::new().write(true).open(&path).unwrap();
        f.set_times(FileTimes::new().set_accessed(when).set_modified(when))
            .unwrap();
    }

    #[test]
    fn py_json_escaping_matches_python() {
        // Values pinned against CPython json.dumps(ensure_ascii=True)
        assert_eq!(py_escape_json_string("a\"b\\c"), r#""a\"b\\c""#);
        assert_eq!(py_escape_json_string("\u{7f}"), "\"\u{7f}\""); // DEL raw
        assert_eq!(py_escape_json_string("é"), r#""\u00e9""#);
        assert_eq!(py_escape_json_string("日本語"), r#""\u65e5\u672c\u8a9e""#);
        assert_eq!(py_escape_json_string("🙂"), r#""\ud83d\ude42""#);
        assert_eq!(py_escape_json_string("\u{1}"), r#""\u0001""#);
        assert_eq!(py_escape_json_string("\u{8}"), r#""\b""#);
        let infos = vec![
            ("w.a".to_owned(), "bfloat16".to_owned(), "[1, 2]".to_owned()),
            ("w.b".to_owned(), "float32".to_owned(), "[]".to_owned()),
        ];
        assert_eq!(
            py_dumps_compressed_vectors(&infos),
            r#"{"w.a": {"dtype": "bfloat16", "shape": "[1, 2]"}, "w.b": {"dtype": "float32", "shape": "[]"}}"#
        );
        assert_eq!(py_dumps_compressed_vectors(&[]), "{}");
    }

    #[test]
    fn dtype_table_matches_safetensors_08() {
        // all 22 dtypes of safetensors 0.8 (tensor.rs Dtype::bitsize)
        let cases = [
            ("BOOL", 8),
            ("F4", 4),
            ("F6_E2M3", 6),
            ("F6_E3M2", 6),
            ("U8", 8),
            ("I8", 8),
            ("F8_E5M2", 8),
            ("F8_E4M3", 8),
            ("F8_E8M0", 8),
            ("F8_E4M3FNUZ", 8),
            ("F8_E5M2FNUZ", 8),
            ("I16", 16),
            ("U16", 16),
            ("F16", 16),
            ("BF16", 16),
            ("I32", 32),
            ("U32", 32),
            ("F32", 32),
            ("C64", 64),
            ("F64", 64),
            ("I64", 64),
            ("U64", 64),
        ];
        for (name, bits) in cases {
            assert_eq!(dtype_bitsize(name), Some(bits), "{name}");
        }
        assert_eq!(dtype_bitsize("FLOAT32"), None);
        assert_eq!(dtype_bitsize(""), None);
    }

    // ---- Phase 6: the display tensor tree ---------------------------------

    fn tensor(name: &str, shape: &[u64]) -> TensorEntry {
        TensorEntry {
            name: name.to_owned(),
            dtype: "BF16".to_owned(),
            shape: shape.to_vec(),
            start: 0,
            end: 0,
        }
    }

    /// Decode the wire form into `(nodes, leaves)` for readable assertions.
    fn decode_tree(json: &str) -> (Vec<serde_json::Value>, Vec<u64>) {
        let parsed: serde_json::Value = serde_json::from_str(json).expect("valid JSON");
        assert_eq!(parsed["v"].as_u64(), Some(u64::from(TENSOR_TREE_VERSION)));
        let nodes = parsed["nodes"].as_array().expect("nodes").clone();
        let leaves = parsed["leaves"]
            .as_array()
            .expect("leaves")
            .iter()
            .map(|v| v.as_u64().expect("leaf index"))
            .collect();
        (nodes, leaves)
    }

    #[test]
    fn tensor_tree_groups_by_dotted_name() {
        // `a.b.w` -> folder a -> folder b -> leaf w; `a.x` -> folder a -> leaf x
        let tensors = vec![
            tensor("a.b.w", &[2, 4]), // 8 params
            tensor("a.x", &[3]),      // 3 params
            tensor("top", &[5]),      // root leaf, 5 params
            tensor("a.b.v", &[1, 1]), // 1 param
        ];
        let (nodes, leaves) = decode_tree(&encode_tensor_tree(&tensors));
        // Only FOLDERS are nodes (`x`, `w`, `v`, `top` are leaves): pre-order
        // root -> a -> b.
        let seg: Vec<&str> = nodes
            .iter()
            .map(|n| n[0].as_str().expect("segment"))
            .collect();
        assert_eq!(seg, ["", "a", "b"]);
        // root has ONE folder child (a) and 1 own leaf (`top`)
        assert_eq!(nodes[0][1].as_u64(), Some(1), "root child folders");
        assert_eq!(nodes[0][2].as_u64(), Some(1), "root own tensors (top)");
        assert_eq!(nodes[0][3].as_u64(), Some(4), "root total count");
        assert_eq!(nodes[0][4].as_u64(), Some(8 + 3 + 5 + 1), "root params");
        // folder a: 1 child (b), 1 own tensor (x), 3 in the subtree
        assert_eq!(nodes[1][1].as_u64(), Some(1));
        assert_eq!(nodes[1][2].as_u64(), Some(1));
        assert_eq!(nodes[1][3].as_u64(), Some(3));
        assert_eq!(nodes[1][4].as_u64(), Some(8 + 3 + 1));
        // folder b: no children, 2 own tensors
        assert_eq!(nodes[2][1].as_u64(), Some(0));
        assert_eq!(nodes[2][2].as_u64(), Some(2));
        assert_eq!(nodes[2][3].as_u64(), Some(2));
        // leaves: own-before-children emission -> root's `top` (2), then
        // folder a's own `x` (1), then a's child b's (0, 3)
        assert_eq!(leaves, vec![2, 1, 0, 3]);
    }

    #[test]
    fn tensor_tree_handles_scalars_unnamed_levels_and_dots_only() {
        let tensors = vec![
            tensor("scale", &[]),   // scalar -> 1 param, root leaf
            tensor("a..b.w", &[2]), // empty level -> "(unnamed)"
            tensor("", &[4]),       // empty name -> root leaf, 4 params
            tensor(".", &[1]),      // two empty segments -> folder + leaf
        ];
        let (nodes, leaves) = decode_tree(&encode_tensor_tree(&tensors));
        let seg: Vec<&str> = nodes
            .iter()
            .map(|n| n[0].as_str().expect("segment"))
            .collect();
        // pre-order: root, `a` -> `(unnamed)` -> `b` (from "a..b.w"), then the
        // root's second folder `(unnamed)` (from ".").
        assert_eq!(seg, ["", "a", "(unnamed)", "b", "(unnamed)"]);
        assert_eq!(nodes[0][2].as_u64(), Some(2), "scale + the empty name");
        assert_eq!(nodes[0][3].as_u64(), Some(4));
        assert_eq!(nodes[0][4].as_u64(), Some(1 + 4 + 2 + 1));
        assert_eq!(leaves, vec![0, 2, 1, 3]);
    }

    #[test]
    fn tensor_tree_leaves_cover_every_tensor_exactly_once() {
        // A MoE-shaped set: 40 layers x 8 experts x 3 projections + per-layer
        // attention, i.e. the folder-heavy layout the fold exists for.
        let mut tensors = Vec::new();
        for layer in 0..40 {
            tensors.push(tensor(
                &format!("model.layers.{layer}.self_attn.q_proj.weight"),
                &[16, 8],
            ));
            for expert in 0..8 {
                for proj in ["gate_proj", "up_proj", "down_proj"] {
                    tensors.push(tensor(
                        &format!("model.layers.{layer}.mlp.experts.{expert}.{proj}.weight"),
                        &[8, 4],
                    ));
                }
            }
        }
        let json = encode_tensor_tree(&tensors);
        let (nodes, leaves) = decode_tree(&json);
        // every tensor index appears exactly once
        let mut sorted = leaves.clone();
        sorted.sort_unstable();
        let expected: Vec<u64> = (0..tensors.len() as u64).collect();
        assert_eq!(sorted, expected);
        // the root aggregate is the whole set
        assert_eq!(nodes[0][3].as_u64(), Some(tensors.len() as u64));
        // 40 layers x (one [16,8] attention = 128 + 24 expert [8,4] = 768)
        assert_eq!(nodes[0][4].as_u64(), Some(40 * (128 + 24 * 32)));
        // sum of own-tensor counts == tensor count (no double counting)
        let own: u64 = nodes.iter().map(|n| n[2].as_u64().expect("t")).sum();
        assert_eq!(own, tensors.len() as u64);
        // pre-order integrity: every node's childCount matches the frame walk
        // (the decoder's next-sibling skip relies on it) — verified by
        // re-walking with a stack and requiring full consumption.
        let mut stack: Vec<(usize, u64)> = vec![(0, 0)];
        let mut seen = 0usize;
        let mut cursor = 0usize;
        while let Some((idx, next)) = stack.last_mut() {
            if *next == 0 {
                seen += 1;
                cursor += nodes[*idx][2].as_u64().expect("t") as usize;
            }
            let children = nodes[*idx][1].as_u64().expect("c");
            if *next < children {
                let child = nth_child(&nodes, *idx, *next as usize);
                *next += 1;
                stack.push((child, 0));
            } else {
                stack.pop();
            }
        }
        assert_eq!(seen, nodes.len(), "every node is visited exactly once");
        assert_eq!(cursor, leaves.len(), "leaf cursor consumed every leaf");
    }

    /// Node index of the `child`-th child of `parent` — the same subtree skip
    /// the frontend decoder precomputes from `childCount`.
    fn nth_child(nodes: &[serde_json::Value], parent: usize, child: usize) -> usize {
        let mut idx = parent + 1;
        for _ in 0..child {
            idx += subtree_size_at(nodes, idx);
        }
        idx
    }

    fn subtree_size_at(nodes: &[serde_json::Value], idx: usize) -> usize {
        let children = nodes[idx][1].as_u64().expect("c") as usize;
        let mut size = 1;
        let mut cursor = idx + 1;
        for _ in 0..children {
            let child_size = subtree_size_at(nodes, cursor);
            size += child_size;
            cursor += child_size;
        }
        size
    }

    #[test]
    fn tensor_tree_json_reads_a_real_file_and_matches_the_header_parse() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("model.safetensors");
        let out = vec![
            entry("blk.0.w", "BF16", &[2, 2], 0, 8),
            entry("blk.1.w", "BF16", &[2], 8, 12),
            entry("bias", "F32", &[4], 12, 28),
        ];
        let image = file_image(
            Some(&[("format".to_owned(), "pt".to_owned())]),
            &out,
            &[0u8; 28],
        );
        std::fs::write(&path, &image).unwrap();

        let tree = tensor_tree_json(&path, 32 * 1024 * 1024).expect("tree");
        let (nodes, leaves) = decode_tree(&tree);
        let seg: Vec<&str> = nodes
            .iter()
            .map(|n| n[0].as_str().expect("segment"))
            .collect();
        assert_eq!(seg, ["", "blk", "0", "1"]);
        assert_eq!(leaves, vec![2, 0, 1], "root leaf first, then blk's");

        // the leaf indices address the SAME tensor order as the header display
        let header = header_display_json(&path, 32 * 1024 * 1024).expect("header");
        let parsed: serde_json::Value = serde_json::from_str(&header).unwrap();
        let names: Vec<&str> = parsed["tensors"]
            .as_array()
            .unwrap()
            .iter()
            .map(|t| t["name"].as_str().unwrap())
            .collect();
        assert_eq!(names, ["blk.0.w", "blk.1.w", "bias"]);
        let resolved: Vec<&str> = leaves.iter().map(|i| names[*i as usize]).collect();
        assert_eq!(resolved, ["bias", "blk.0.w", "blk.1.w"]);
    }

    #[test]
    fn tensor_tree_json_reports_the_same_failures_as_the_header_parse() {
        let dir = tempfile::tempdir().unwrap();
        let missing = dir.path().join("gone.safetensors");
        assert!(tensor_tree_json(&missing, 1024).is_err());
        // a header larger than the cap is refused (B4 guard parity)
        let path = dir.path().join("big.safetensors");
        let out = vec![entry("w", "F32", &[1], 0, 4)];
        let image = file_image(None, &out, &[0u8; 4]);
        std::fs::write(&path, &image).unwrap();
        assert!(
            tensor_tree_json(&path, 4).is_err(),
            "cap too small for the header"
        );
        assert!(tensor_tree_json(&path, 1024).is_ok());
    }
}
