//! safetensors container I/O — mmap reads, an order-preserving canonical
//! writer and atomic replacement (Plan §4.2.1 `safetensors_io.rs`, §4.3,
//! §4.4.4, §4.7.4).
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
//! # Why Neo writes its own header (Plan §4.7.4)
//!
//! The reference `serialize` re-sorts tensors and re-randomises metadata key
//! order (its metadata map is a `HashMap`), so a torch-mediated round trip
//! only restores the original bytes by luck. Neo's writer instead **preserves
//! the source file's JSON key order and metadata order** and reproduces the
//! canonical byte format, which makes decompression **byte-exact** for every
//! file a standard tool wrote — and that guarantee is what turns
//! `znn_neo_src_sha256` (Plan §4.4.3) into a real end-to-end check.
//! [`StContainer::canonical`] records whether a parsed file matches the
//! canonical form byte-for-byte; sources that do not (hand-edited headers,
//! exotic writers) still compress, but their restore is guaranteed at the
//! weaker "tensor data + metadata values equal" level (Plan §4.7.4) and the
//! pipeline says so instead of failing the sha check blindly.
//!
//! All writes go through [`AtomicWriter`]: sibling `.tmp` → write → fsync →
//! rename → fsync(parent dir) (Plan §4.4.4 — the legacy Python path has no
//! fsync at all). ENOSPC surfaces as [`StError::Io`] with the partial file
//! removed; nothing is ever renamed into place unverified.

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

    /// Parse from a file path via a read-only shared mmap (Plan §4.3: the
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
        // `safe_open` mmaps identically, Plan §7 R4: shared read mappings
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
            if tensors.iter().any(|t| *t.name == k) {
                odd = true; // duplicate tensor name (serde: last wins)
            }
            let entry = parse_tensor_entry(&mut j, &k, &mut odd)?;
            // duplicate-name semantics of serde: the LAST value wins
            if let Some(pos) = tensors.iter().position(|t| *t.name == k) {
                tensors[pos] = entry;
            } else {
                tensors.push(entry);
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

// ---------------------------------------------------------------------------
// Atomic writer (Plan §4.4.4)
// ---------------------------------------------------------------------------

/// Sibling-tempfile atomic writer with optional inline SHA-256 (Plan
/// §4.4.3: the decompressor verifies WITHOUT re-reading the file — the
/// hasher consumes every byte exactly once on its way to disk).
///
/// Lifecycle: `new` creates `<dst>.tmp` (the legacy naming, so the startup
/// cleanup and the route-level failure cleanup recognise it) → `write_all`
/// streams → [`finish`](Self::finish) flushes + fsyncs (the file is durable
/// but still a tmp) → the caller VERIFIES → [`commit`](Self::commit) renames
/// into place + fsyncs the parent directory (Plan §4.4.4: the original is
/// only ever replaced after verification succeeded). Any error — or a plain
/// `drop` without `commit` (panic, process kill) — removes the partial file.
pub struct AtomicWriter {
    tmp: PathBuf,
    dst: PathBuf,
    inner: Option<BufWriter<File>>,
    hasher: Option<Sha256>,
    written: u64,
    committed: bool,
}

impl AtomicWriter {
    /// Create `<dst>.tmp` beside the destination (same filesystem ⇒ the
    /// rename is atomic) and start writing.
    ///
    /// # Errors
    /// Open/create failures (including a read-only or full filesystem —
    /// the ENOSPC surfaces on the first write at the latest).
    pub fn new(dst: &Path, with_sha256: bool) -> StResult<Self> {
        let tmp = tmp_sibling(dst);
        let file = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&tmp)?;
        Ok(Self {
            tmp,
            dst: dst.to_path_buf(),
            inner: Some(BufWriter::with_capacity(1024 * 1024, file)),
            hasher: with_sha256.then(Sha256::new),
            written: 0,
            committed: false,
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
    /// (Plan §4.4.4 — makes the replacement itself crash-durable).
    ///
    /// # Errors
    /// Rename/fsync failures (the tmp is kept for diagnostics in that case —
    /// it is a complete, verified artifact; the Drop guard removes it only
    /// when the writer is dropped WITHOUT commit).
    pub fn commit(&mut self) -> StResult<()> {
        if self.inner.is_some() {
            return Err(StError::Format("commit before finish".to_owned()));
        }
        std::fs::rename(&self.tmp, &self.dst)?;
        fsync_dir(self.dst.parent().unwrap_or_else(|| Path::new(".")))?;
        self.committed = true;
        Ok(())
    }

    /// Abort: remove the partial (or finished-but-uncommitted) file
    /// (by-reference so scoped error paths can abort and still return the
    /// error through the enclosing function).
    pub fn abort(&mut self) {
        self.inner = None;
        self.committed = true; // suppress the Drop guard
        let _ = std::fs::remove_file(&self.tmp);
    }

    /// Verification-failure path (Plan §4.4.3): preserve the finished tmp as
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
        fsync_dir(path.parent().unwrap_or_else(|| Path::new(".")))?;
        self.committed = true; // the tmp now lives on AS `path`
        Ok(())
    }
}

impl Drop for AtomicWriter {
    fn drop(&mut self) {
        // A writer dropped WITHOUT commit() (error path, panic, kill, failed
        // verification) must never leave a stray `.tmp` behind (Plan §4.4.4).
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

/// fsync a directory (POSIX): makes the rename itself durable (Plan §4.4.4).
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
/// worker thread while the tensor loop runs — Plan §4.4.3 step 1).
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
        std::fs::remove_dir_all(&dir).ok();
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
}
