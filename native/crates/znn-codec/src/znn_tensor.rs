//! Per-tensor ZipNN blobs — the container semantics the official
//! `zipnn_compress_safetensors.py` / Neo's legacy `py/compress.py` apply to
//! every tensor of a safetensors file (Plan §4.5, Appendix B), extended in
//! Phase 4 to the FULL safetensors 0.8 dtype set (Plan §4.6, KPI K14).
//!
//! A compressed tensor is stored as a 1-D `U8` vector holding one COMPLETE
//! ZN container: `[32-byte header][packed shape][codec payload]`, built with
//! `input_format = TORCH` and the ORIGINAL tensor's dtype code + shape.
//! Compatibility-band blobs (f32/f16/bf16/fp8) carry the exact codes and
//! mode bytes the official tooling writes, so the official
//! `zipnn_safetensors()` loaders and scripts decode Neo's files unchanged
//! (Plan §4.6.3). Neo-extension-band blobs (f64, complex64, integers, BOOL,
//! FNUZ/MX floats — codes 128–146) are self-describing for Neo and rejected
//! with an EXPLICIT error by official tools (demonstrated: `ValueError:
//! Unsupported Dtype N`; L5 section E pins it) — files containing them are
//! marked `znn_neo_extended="1"` and badged in the UI (Plan §4.6.4).
//!
//! Parameter mapping (compatibility band verified against
//! `third_party/zipnn/zipnn.py` `compress_torch_numpy_byte` /
//! `decompress_bin` and production header dumps, 2026-09-24; the extension
//! band follows the Plan §4.6.2/§4.6.3 tables and `dtype.rs`):
//!
//! | safetensors dtype | code | torch name        | planes | bit_reorder | byte_reorder | chunk        |
//! |-------------------|------|-------------------|--------|-------------|--------------|--------------|
//! | F32               | 1    | float32           | 4      | 1           | 220          | 256 KiB      |
//! | F16               | 4    | float16           | 2      | 0           | 10           | 256 KiB      |
//! | BF16              | 6    | bfloat16          | 2      | 1           | 10           | 256 KiB      |
//! | F8_E4M3           | 29   | float8_e4m3fn     | 1      | 1 (ignored) | 10           | **128 KiB**  |
//! | F8_E5M2           | 30   | float8_e5m2       | 1      | 1 (ignored) | 10           | **128 KiB**  |
//! | F64               | 128  | float64           | 8      | 1 (f64)     | 88           | 256 KiB      |
//! | C64 (=2×f32)      | 130  | complex64         | 4      | 1 (f32)     | 220          | 256 KiB      |
//! | I8/U8/BOOL        | 132–134 | int8/uint8/bool| 1      | 0           | 10           | **128 KiB**  |
//! | I16/U16           | 135/136 | int16/uint16    | 2      | 0           | 10 (+1/8)    | 256 KiB      |
//! | I32/U32           | 137/138 | int32/uint32    | 4      | 0           | 220 (+41/9/1)| 256 KiB      |
//! | I64/U64           | 139/140 | int64/uint64    | 8      | 0           | 88           | 256 KiB      |
//! | F8_E4M3FNUZ       | 141  | float8_e4m3fnuz   | 1      | 0           | 10           | **128 KiB**  |
//! | F8_E5M2FNUZ       | 142  | float8_e5m2fnuz   | 1      | 0           | 10           | **128 KiB**  |
//! | F8_E8M0           | 143  | float8_e8m0fnu    | 1      | 0           | 10           | **128 KiB**  |
//! | F4                | 144  | float4_e2m1fn_x2  | 1      | 0           | 10           | **128 KiB**  |
//! | F6_E2M3           | 145  | F6_E2M3 (see below)| 1     | 0           | 10           | **128 KiB**  |
//! | F6_E3M2           | 146  | F6_E3M2 (see below)| 1     | 0           | 10           | **128 KiB**  |
//!
//! The FP8 chunk quirk: `zipnn.py` always writes `compression_chunk_log2=18`
//! into byte 14 but passes `min(128 KiB, chunk)` to the C core when
//! `num_buf == 1` (`HUF_BLOCKSIZE_MAX` bound) — both the compressor and the
//! decompressor must apply the clamp, never the raw header value. Neo's own
//! single-plane extension types follow the same rule (a 256 KiB plane would
//! exceed the huff0 block maximum and every chunk would store raw).
//!
//! `(+1/8)` / `(+41/9/1)`: the truncation modes — [`select_truncation`]
//! drops byte planes that are zero across the WHOLE tensor (lossless by
//! construction; see `dtype.rs` module docs for the container semantics).
//!
//! Torch names: recorded verbatim in `znn_compressed_vectors` infos. torch
//! 2.14 has no `float6_*` dtype (verified on the release build — the Plan's
//! §4.6.1 "shell dtype" note predates the release), so the two F6 types
//! record their safetensors names instead; every other dtype records its
//! `str(torch.dtype)` minus the `torch.` prefix. `complex128`/`bcomplex32`
//! (codes 129/131) exist in torch but have NO safetensors 0.8
//! representation — their schemes are codec-level (direct round-trips work;
//! the safetensors pipeline refuses to restore such blobs with an explicit
//! error, since no valid output header could name them).
//!
//! The legacy path (`py/compress.py`, vendored zipnn) RAISES on everything
//! outside f32/bf16/f16/fp8 (`ValueError: Support only torch.dtype …`);
//! Neo compresses the full dtype set — strictly more capable, same file
//! format. Legacy DEcompression of a Neo-extension file fails with the
//! vendored decoder's explicit `ValueError: Unsupported Dtype N` (no silent
//! corruption), which is the documented migration behaviour until the
//! legacy path is removed (Phase 8).

use std::sync::atomic::AtomicBool;

use crate::codec::{self, CoreParams};
use crate::dtype::{self, Band, PlaneScheme};
use crate::header::{InputFormat, ZnHeader, pack_shape};
use crate::{CodecError, CodecResult, HUF_BLOCKSIZE_MAX};

/// ZipNN container version Neo writes (0.5.4 — the vendored/upstream
/// generation; `zipnn.py _version_major/minor/tiny`).
pub const ZNN_VERSION: [u8; 3] = [0, 5, 4];

/// One row of the dtype table: the header code, the safetensors dtype
/// string, the torch name recorded in infos, and the canonical
/// `bit_reorder` header byte.
struct DtypeEntry {
    code: u8,
    st: &'static str,
    torch: &'static str,
    bit_reorder: u8,
}

/// THE dtype table (single source of truth for both directions). Codes and
/// plane geometry come from Plan §4.6.3 / `dtype.rs`; torch names were
/// verified against torch 2.14.0 (`str(torch.<name>)`) and safetensors 0.8
/// header spellings against the pip package, 2026-09-26.
///
/// `C128`/`BC32` are Neo codec-level pseudo-names for complex128 /
/// bcomplex32: real torch dtypes WITHOUT a safetensors 0.8 representation
/// (a `.safetensors` file can never contain them — `StContainer::parse`
/// rejects unknown dtype strings — so their blobs can only reach the
/// decoder hand-crafted, and the pipeline refuses to restore them).
const DTYPE_TABLE: &[DtypeEntry] = &[
    // compatibility band (official-decodable)
    DtypeEntry {
        code: dtype::FLOAT32,
        st: "F32",
        torch: "float32",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::FLOAT16,
        st: "F16",
        torch: "float16",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::BFLOAT16,
        st: "BF16",
        torch: "bfloat16",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::FLOAT8_E4M3FN,
        st: "F8_E4M3",
        torch: "float8_e4m3fn",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::FLOAT8_E5M2,
        st: "F8_E5M2",
        torch: "float8_e5m2",
        bit_reorder: 1,
    },
    // Neo extension band (Plan §4.6.3 codes 128–146)
    DtypeEntry {
        code: dtype::NEO_F64,
        st: "F64",
        torch: "float64",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::NEO_COMPLEX128,
        st: "C128",
        torch: "complex128",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::NEO_COMPLEX64,
        st: "C64",
        torch: "complex64",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::NEO_BCOMPLEX32,
        st: "BC32",
        torch: "bcomplex32",
        bit_reorder: 1,
    },
    DtypeEntry {
        code: dtype::NEO_I8,
        st: "I8",
        torch: "int8",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_U8,
        st: "U8",
        torch: "uint8",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_BOOL,
        st: "BOOL",
        torch: "bool",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_I16,
        st: "I16",
        torch: "int16",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_U16,
        st: "U16",
        torch: "uint16",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_I32,
        st: "I32",
        torch: "int32",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_U32,
        st: "U32",
        torch: "uint32",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_I64,
        st: "I64",
        torch: "int64",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_U64,
        st: "U64",
        torch: "uint64",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_F8_E4M3FNUZ,
        st: "F8_E4M3FNUZ",
        torch: "float8_e4m3fnuz",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_F8_E5M2FNUZ,
        st: "F8_E5M2FNUZ",
        torch: "float8_e5m2fnuz",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_F8_E8M0,
        st: "F8_E8M0",
        torch: "float8_e8m0fnu",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_F4,
        st: "F4",
        torch: "float4_e2m1fn_x2",
        bit_reorder: 0,
    },
    // torch 2.14 has no float6 dtype (verified) — infos record the
    // safetensors name so the record stays truthful
    DtypeEntry {
        code: dtype::NEO_F6_E2M3,
        st: "F6_E2M3",
        torch: "F6_E2M3",
        bit_reorder: 0,
    },
    DtypeEntry {
        code: dtype::NEO_F6_E3M2,
        st: "F6_E3M2",
        torch: "F6_E3M2",
        bit_reorder: 0,
    },
];

/// The compression-band scheme for one dtype: everything needed to build
/// (or interpret) its ZN blob header plus the codec geometry.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TensorScheme {
    /// Header byte 15 dtype code.
    pub dtype_code: u8,
    /// safetensors dtype string of the original tensor (`"BF16"`, …).
    pub st_dtype: &'static str,
    /// torch dtype name recorded in `znn_compressed_vectors`
    /// (`str(tensor.dtype)` without the `torch.` prefix; the two F6 types
    /// record their safetensors name — no torch spelling exists).
    pub torch_name: &'static str,
    /// Plane count (`num_buf`) = the transform word size.
    pub num_planes: usize,
    /// True bit width of one dtype ELEMENT (F4 = 4, F6 = 6, C64 = 64 — two
    /// f32 words; byte-aligned types `num_planes * 8`). The blob shape
    /// check is `nelem × bits / 8 == original_len` (reference semantics).
    pub bits_per_elem: usize,
    /// Header byte 6 (`bits_mode`) Neo writes for this dtype.
    pub bit_reorder: u8,
    /// Header byte 5 (`bytes_mode`) — the canonical mode, or the truncation
    /// mode [`select_truncation`] chose (never for compatibility dtypes).
    pub byte_reorder: u8,
    /// Interoperability band of the code.
    pub band: Band,
    /// Truncation modes this dtype may carry (empty unless it is a Neo
    /// integer type with truncation support).
    pub trunc_modes: &'static [u8],
}

impl TensorScheme {
    /// Build the scheme of a table entry (geometry from `dtype.rs` — the
    /// single source of truth for planes/bits/truncation).
    fn from_entry(entry: &DtypeEntry, plane: PlaneScheme) -> Self {
        Self {
            dtype_code: entry.code,
            st_dtype: entry.st,
            torch_name: entry.torch,
            num_planes: plane.num_planes,
            bits_per_elem: plane.bits_per_elem,
            bit_reorder: entry.bit_reorder,
            byte_reorder: plane.canonical_mode(),
            band: plane.band,
            trunc_modes: plane.trunc_modes,
        }
    }

    /// Whether blobs of this scheme are Neo-extension (official tools reject
    /// them; the file needs the `znn_neo_extended` marker).
    #[must_use]
    pub const fn is_neo(&self) -> bool {
        matches!(self.band, Band::Neo)
    }

    /// Whether `byte_reorder` is a legal mode for this dtype (canonical or
    /// one of its truncation modes).
    #[must_use]
    pub fn allows_mode(&self, byte_reorder: u8) -> bool {
        byte_reorder == self.byte_reorder_original() || self.trunc_modes.contains(&byte_reorder)
    }

    /// The canonical mode of the dtype (independent of any truncation
    /// currently selected in `byte_reorder`).
    #[must_use]
    pub fn byte_reorder_original(&self) -> u8 {
        match self.num_planes {
            4 => dtype::MODE_4PLANES,
            8 => dtype::MODE_8PLANES,
            _ => dtype::MODE_2PLANES,
        }
    }

    /// Bytes per element for byte-aligned dtypes (test/capacity helper).
    ///
    /// # Panics
    /// Sub-byte dtypes (F4/F6) — use [`TensorScheme::bits_per_elem`].
    #[must_use]
    pub fn bytes_per_elem(&self) -> usize {
        assert_eq!(self.bits_per_elem % 8, 0, "sub-byte dtype");
        self.bits_per_elem / 8
    }
}

/// The scheme for a safetensors dtype string (compress direction), or
/// `None` when the string is not a dtype Neo compresses. Since Phase 4
/// this covers the FULL safetensors 0.8 set (all 22 spellings) plus the
/// codec-level pseudo-names `C128`/`BC32`.
#[must_use]
pub fn scheme_for_st_dtype(st_dtype: &str) -> Option<TensorScheme> {
    let entry = DTYPE_TABLE.iter().find(|e| e.st == st_dtype)?;
    // plane geometry validated at table-construction consistency level:
    // every table code exists in dtype.rs (unit-tested below)
    let plane = dtype::scheme_for_dtype(entry.code).ok()?;
    Some(TensorScheme::from_entry(entry, plane))
}

/// The scheme for a header dtype CODE, accepting the upstream alias codes
/// (2=FLOAT→F32, 5=HALF→F16) the way `zipnn.py decompress_bin` does.
///
/// # Errors
/// Codes outside the compatibility band and the assigned Neo extension
/// codes (128–146).
pub fn scheme_for_code(code: u8) -> CodecResult<TensorScheme> {
    let canonical = match code {
        dtype::FLOAT => dtype::FLOAT32,
        dtype::HALF => dtype::FLOAT16,
        other => other,
    };
    let entry = DTYPE_TABLE
        .iter()
        .find(|e| e.code == canonical)
        .ok_or_else(|| {
            // keep the historical, user-facing error wording for the bands
            if dtype::is_neo_code(code) {
                CodecError::Unsupported(format!(
                    "dtype code {code} is an unassigned Neo extension-band code — this file needs a newer Neo (Plan §4.6.3 assigns 128–146)"
                ))
            } else {
                CodecError::Unsupported(format!(
                    "dtype code {code} is not produced by any ZipNN safetensors path (upstream-only codes are dead in the official codec too; Neo extension band starts at 128)"
                ))
            }
        })?;
    let plane = dtype::scheme_for_dtype(entry.code)?;
    Ok(TensorScheme::from_entry(entry, plane))
}

/// The safetensors dtype string + torch name for a header dtype CODE (the
/// decompression direction; accepts the alias codes 2=FLOAT and 5=HALF).
///
/// # Errors
/// Codes outside the compatibility band and the assigned Neo extension
/// codes.
pub fn st_dtype_for_code(code: u8) -> CodecResult<(&'static str, &'static str)> {
    let scheme = scheme_for_code(code)?;
    Ok((scheme.st_dtype, scheme.torch_name))
}

/// The effective codec chunk for a scheme: the production 256 KiB, clamped
/// to `HUF_BLOCKSIZE_MAX` for single-plane data — the `zipnn.py` fp8 quirk,
/// which every 1-plane type needs (a 256 KiB plane exceeds the huff0 block
/// maximum and would store raw).
#[must_use]
pub fn effective_chunk(scheme: &TensorScheme) -> usize {
    if scheme.num_planes == 1 {
        HUF_BLOCKSIZE_MAX.min(crate::DEFAULT_CHUNK)
    } else {
        crate::DEFAULT_CHUNK
    }
}

fn core_params(scheme: &TensorScheme, threads: usize) -> CoreParams {
    CoreParams {
        num_buf: scheme.num_planes,
        bit_reorder: scheme.bit_reorder,
        byte_reorder: scheme.byte_reorder,
        chunk: effective_chunk(scheme),
        threshold: crate::DEFAULT_THRESHOLD,
        threads,
    }
}

/// Choose the truncation mode of a Neo integer tensor from its zero-byte
/// statistics (Plan §6.2 Phase 4 "ゼロ統計自動選択"): the largest byte
/// plane suffix (or, for 2-plane words, the low plane) that is ZERO across
/// the whole tensor is dropped from the payload and reconstructed as zeros
/// on decode — lossless by construction. Returns the scheme with the
/// adjusted `byte_reorder` (unchanged when no truncation applies).
///
/// Only the truncation-capable Neo integer types participate (I16/U16 via
/// modes 1/8, I32/U32 via 41/9/1 — `dtype.rs`); compatibility dtypes and
/// everything else return the input scheme untouched. The C reference for
/// the statistics is `count_zero_bytes` (dead code there — the modes were
/// never selectable; Neo formalises them).
#[must_use]
pub fn select_truncation(scheme: &TensorScheme, data: &[u8]) -> TensorScheme {
    let n = scheme.num_planes;
    if scheme.trunc_modes.is_empty() || data.is_empty() || data.len() % n != 0 {
        return *scheme;
    }
    // `keep` = the number of low byte planes that must survive; positions
    // keep..n are all-zero. Probe top-down with early exit: the common case
    // (top byte non-zero somewhere) costs a handful of bytes.
    let mut keep = n;
    while keep > 1 {
        let p = keep - 1;
        if data.chunks_exact(n).any(|w| w[p] != 0) {
            break;
        }
        keep = p;
    }
    let mode = match (n, keep) {
        (2, 1) => Some(dtype::MODE_TRUNC_LOW1),
        (4, 3) => Some(dtype::MODE_TRUNC_LOW3_OF4),
        (4, 2) => Some(dtype::MODE_TRUNC_LOW2_OF4),
        (4, 1) => Some(dtype::MODE_TRUNC_LOW1),
        _ => None,
    };
    // 2-plane special case: the LOW byte plane all-zero (multiples of 256)
    // → keep the high plane only (C mode 8)
    let mode = match mode {
        Some(m) => Some(m),
        None if n == 2 && !data.chunks_exact(2).any(|w| w[0] != 0) => {
            Some(dtype::MODE_TRUNC_HIGH1_OF2)
        }
        None => None,
    };
    let Some(mode) = mode else {
        return *scheme;
    };
    debug_assert!(scheme.trunc_modes.contains(&mode));
    TensorScheme {
        byte_reorder: mode,
        ..*scheme
    }
}

/// Build the 32-byte header + packed shape prefix of one tensor blob
/// (TORCH input format, the original dtype code, byte 14 = log2 of the
/// UNCLAMPED configured chunk — production quirk: 1-plane blobs also
/// carry 18 while their payload is chunked at 128 KiB).
#[must_use]
pub fn tensor_header(scheme: &TensorScheme, original_len: u64, shape: &[u64]) -> Vec<u8> {
    let h = ZnHeader {
        version: ZNN_VERSION,
        byte_reorder: scheme.byte_reorder,
        bit_reorder: scheme.bit_reorder,
        method: crate::header::METHOD_HUFFMAN,
        input_format: InputFormat::Torch,
        delta_compressed_type: 0,
        lossy: [0, 0, 0],
        streaming: false,
        streaming_chunk_log2: 0,
        compression_chunk_log2: crate::DEFAULT_CHUNK_LOG2,
        dtype_code: scheme.dtype_code,
        original_len,
        comp_len_field: 0,
    };
    let mut out = h.encode().to_vec();
    out.extend_from_slice(&pack_shape(shape));
    out
}

/// Compress one tensor's raw bytes into a full ZN blob (header + shape +
/// payload). The caller applies the "not worth it" rule (`blob.len() >=
/// data.len()` → store the tensor untouched), exactly like the official
/// script and the legacy pipeline.
///
/// # Errors
/// Codec/parameter errors (propagated) and cancellation.
pub fn compress_tensor(
    scheme: &TensorScheme,
    data: &[u8],
    shape: &[u64],
    threads: usize,
    cancel: Option<&AtomicBool>,
) -> CodecResult<Vec<u8>> {
    let mut out = Vec::new();
    compress_tensor_into(&mut out, scheme, data, shape, threads, cancel)?;
    Ok(out)
}

/// [`compress_tensor`] into a caller-owned, grow-only buffer — the Phase-2
/// pipeline reuses one blob buffer for every tensor of a file (no
/// per-tensor allocation; every byte is overwritten by the assembly).
///
/// # Errors
/// Everything [`compress_tensor`] reports.
pub fn compress_tensor_into(
    out: &mut Vec<u8>,
    scheme: &TensorScheme,
    data: &[u8],
    shape: &[u64],
    threads: usize,
    cancel: Option<&AtomicBool>,
) -> CodecResult<()> {
    let header = tensor_header(scheme, data.len() as u64, shape);
    codec::zipnn_core_into(out, &header, data, &core_params(scheme, threads), cancel)
}

/// Header-level description of what a blob restores to (no payload).
#[derive(Debug, PartialEq, Eq)]
pub struct RestoredInfo {
    /// safetensors dtype string of the ORIGINAL tensor (e.g. `"BF16"`;
    /// `C128`/`BC32` are the codec-level pseudo-names — the safetensors
    /// pipeline refuses to restore those, see the module docs).
    pub st_dtype: &'static str,
    /// torch dtype name as recorded in `znn_compressed_vectors`.
    pub torch_name: &'static str,
    /// Shape from the blob's packed header.
    pub shape: Vec<u64>,
    /// Restored payload length in bytes (the header's `original_len`).
    pub len: u64,
    /// The scheme the blob decodes with (band, modes, geometry).
    pub scheme: TensorScheme,
}

/// The effective decode chunk of a blob header — zipnn.py's fp8 clamp
/// (`compression_chunk if num_buf != 1 else min(128K, compression_chunk)`),
/// applied to every single-plane type (module docs).
fn blob_chunk(header: &ZnHeader, num_planes: usize) -> CodecResult<usize> {
    let chunk_hint = header.validate_for_decode()?;
    Ok(if num_planes == 1 {
        chunk_hint.min(HUF_BLOCKSIZE_MAX)
    } else {
        chunk_hint
    })
}

/// Parse + validate a blob's container prefix WITHOUT decoding the payload
/// (the decompression pipeline's planning pass: the restored header must be
/// known before any tensor is decoded).
///
/// # Errors
/// Everything [`decompress_tensor`] reports about the header/shape, plus
/// the band-strict mode gate: a blob's `byte_reorder` must be the canonical
/// mode of its dtype code or one of ITS truncation modes (compatibility
/// blobs therefore stay canonical-only — official encoders never write
/// truncation modes, and Neo must not reinterpret a compat blob through
/// extension semantics).
pub fn inspect_tensor(blob: &[u8]) -> CodecResult<RestoredInfo> {
    let (header, shape, _used) = ZnHeader::parse(blob)?;
    let scheme = scheme_for_code(header.dtype_code)?;
    if !scheme.allows_mode(header.byte_reorder) {
        return Err(CodecError::Unsupported(format!(
            "byte_reorder {} is not valid for dtype code {} / {} (canonical {}, truncation modes {:?} — Plan §4.6.3)",
            header.byte_reorder,
            header.dtype_code,
            scheme.st_dtype,
            scheme.byte_reorder_original(),
            scheme.trunc_modes
        )));
    }
    // run the chunk derivation too — it is part of the decode contract and
    // must not fail later than the plan
    let _chunk = blob_chunk(&header, scheme.num_planes)?;
    let nelem = shape
        .iter()
        .try_fold(1u64, |a, &d| a.checked_mul(d))
        .ok_or_else(|| CodecError::Shape("shape product overflows".to_owned()))?;
    // reference shape check with SUB-BYTE dtypes (F4 = 4 bits, F6 = 6):
    // nelem × bits must land on a byte boundary and equal original_len
    let total_bits = nelem
        .checked_mul(scheme.bits_per_elem as u64)
        .ok_or_else(|| CodecError::Shape("tensor size overflows".to_owned()))?;
    if total_bits % 8 != 0 {
        return Err(CodecError::Shape(format!(
            "packed shape {shape:?} × {} bits does not end on a byte boundary",
            scheme.bits_per_elem
        )));
    }
    let expect = total_bits / 8;
    if expect != header.original_len {
        return Err(CodecError::Shape(format!(
            "packed shape {shape:?} × {} bits implies {expect} bytes but the header declares original_len {}",
            scheme.bits_per_elem, header.original_len
        )));
    }
    Ok(RestoredInfo {
        st_dtype: scheme.st_dtype,
        torch_name: scheme.torch_name,
        shape,
        len: header.original_len,
        scheme,
    })
}

/// What [`decompress_tensor`] recovered.
#[derive(Debug, PartialEq, Eq)]
pub struct RestoredTensor {
    /// safetensors dtype string of the ORIGINAL tensor (e.g. `"BF16"`).
    pub st_dtype: &'static str,
    /// torch dtype name as recorded in `znn_compressed_vectors`.
    pub torch_name: &'static str,
    /// Shape from the blob's packed header.
    pub shape: Vec<u64>,
    /// The restored raw bytes.
    pub data: Vec<u8>,
}

/// Decompress one ZN blob back to the original tensor bytes, validating the
/// container the way `zipnn.py decompress_bin` does (dtype code → plane
/// scheme, single-plane chunk clamp) plus the hostile-input guards of the
/// codec and the band-strict mode gate.
///
/// # Errors
/// Invalid/hostile blobs (header, shape, payload), unsupported dtype codes,
/// illegal mode/dtype combinations, delta/streaming containers, and an
/// `original_len` inconsistent with the packed shape.
pub fn decompress_tensor(
    blob: &[u8],
    threads: usize,
    cancel: Option<&AtomicBool>,
) -> CodecResult<RestoredTensor> {
    let mut data = Vec::new();
    // built-in sanity bound mirroring the codec's fallback cap (hostile
    // headers may declare any original_len — refuse allocations the blob
    // could not plausibly describe)
    let cap = (blob.len() * 64).max(16 * 1024 * 1024);
    let info = decompress_tensor_into(blob, &mut data, threads, cancel, cap)?;
    Ok(RestoredTensor {
        st_dtype: info.st_dtype,
        torch_name: info.torch_name,
        shape: info.shape,
        data,
    })
}

/// [`decompress_tensor`] into a caller-owned grow-only buffer (the pipeline
/// reuses one buffer across tensors — no per-tensor allocation, and
/// `resize` zero-fills only the growth delta while the decode overwrites
/// every byte).
///
/// # Errors
/// Everything [`decompress_tensor`] reports.
pub fn decompress_tensor_into(
    blob: &[u8],
    out: &mut Vec<u8>,
    threads: usize,
    cancel: Option<&AtomicBool>,
    max_len: usize,
) -> CodecResult<RestoredInfo> {
    let (header, _shape, used) = ZnHeader::parse(blob)?;
    let info = inspect_tensor(blob)?;
    let scheme = info.scheme;
    // zipnn.py decompress_bin: num_buf from the dtype; chunk =
    // `compression_chunk if num_buf != 1 else min(128K, compression_chunk)`.
    let chunk = blob_chunk(&header, scheme.num_planes)?;
    let params = CoreParams {
        num_buf: scheme.num_planes,
        bit_reorder: header.bit_reorder,
        byte_reorder: header.byte_reorder,
        chunk,
        threshold: crate::DEFAULT_THRESHOLD,
        threads,
    };
    let orig_len = usize::try_from(info.len).map_err(|_| {
        CodecError::Size(format!(
            "original_len {} does not fit this platform",
            info.len
        ))
    })?;
    // allocation cap BEFORE the resize (Plan §4.4.2: hostile headers must
    // never bomb the allocator — an OOM abort would kill ComfyUI itself)
    if orig_len > max_len {
        return Err(CodecError::Size(format!(
            "blob declares original_len {orig_len} above the {max_len}-byte restore cap (hostile or truncated header?)"
        )));
    }
    out.clear();
    out.resize(orig_len, 0);
    codec::combine_dtype_into(out, &blob[used..], &params, cancel)?;
    Ok(info)
}

/// The Python `str(list(shape))` rendering recorded in the infos map
/// (`"[1, 2]"`, `"[]"` for scalars) — Rust's `{:?}` on `Vec<u64>` is
/// byte-identical to it (same brackets, same ", " separator).
#[must_use]
pub fn shape_string(shape: &[u64]) -> String {
    format!("{shape:?}")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(dtype: &str, n: usize, low_entropy: bool, _shape: &[u64]) -> Vec<u8> {
        let scheme = scheme_for_st_dtype(dtype).expect("band dtype");
        // sub-byte dtypes (F4/F6) generate PACKED BYTES: `n` is the byte
        // count for them (the `_` arm pushes one byte per iteration)
        let per_elem = if scheme.bits_per_elem < 8 {
            1
        } else {
            scheme.bytes_per_elem()
        };
        let mut data = Vec::with_capacity(n * per_elem);
        let mut x = 12345u32;
        for i in 0..n {
            x = x.wrapping_mul(1664525).wrapping_add(1013904223);
            match dtype {
                "F32" => {
                    let f = if low_entropy {
                        ((x >> 8) as f32 / 8_388_608.0 - 1.0) * 0.01
                    } else {
                        f32::from_bits(x)
                    };
                    data.extend_from_slice(&f.to_le_bytes());
                }
                "F64" => {
                    let f = if low_entropy {
                        ((x >> 8) as f64 / 8_388_608.0 - 1.0) * 0.01
                    } else {
                        f64::from_bits(u64::from(x) | (u64::from(x) << 32))
                    };
                    data.extend_from_slice(&f.to_le_bytes());
                }
                "C64" => {
                    let re = ((x >> 8) as f32 / 8_388_608.0 - 1.0) * 0.01;
                    let im = ((x >> 9) as f32 / 8_388_608.0) * 0.02;
                    data.extend_from_slice(&re.to_le_bytes());
                    data.extend_from_slice(&im.to_le_bytes());
                }
                "BF16" => {
                    let v: u16 = if low_entropy {
                        (0x3F80 | ((x >> 9) & 0x7F)) as u16
                    } else {
                        (x >> 16) as u16
                    };
                    data.extend_from_slice(&v.to_le_bytes());
                }
                "F16" => {
                    let v: u16 = if low_entropy {
                        (0x3C00 | ((x >> 10) & 0x1FF)) as u16
                    } else {
                        (x >> 16) as u16
                    };
                    data.extend_from_slice(&v.to_le_bytes());
                }
                "I16" | "U16" => {
                    let v: u16 = if low_entropy {
                        (x % 200) as u16
                    } else {
                        (x >> 16) as u16
                    };
                    data.extend_from_slice(&v.to_le_bytes());
                }
                "I32" | "U32" => {
                    let v: u32 = if low_entropy { x % 40_000 } else { x };
                    data.extend_from_slice(&v.to_le_bytes());
                }
                "I64" | "U64" => {
                    let v: u64 = if low_entropy {
                        u64::from(x % 100_000)
                    } else {
                        u64::from(x) | (u64::from(!x) << 32)
                    };
                    data.extend_from_slice(&v.to_le_bytes());
                }
                "BOOL" => {
                    let b: u8 = if low_entropy {
                        u8::from(i % 4 == 0)
                    } else {
                        u8::from(x & 1 != 0)
                    };
                    data.push(b);
                }
                _ => {
                    // opaque byte payloads (fp8 family, F4/F6, I8/U8)
                    let b: u8 = if low_entropy {
                        (0x38 | ((x >> 12) & 0x7)) as u8
                    } else {
                        ((x >> 16) & 0x7F) as u8
                    };
                    data.push(b);
                }
            }
        }
        data
    }

    /// Every dtype of the table, at several sizes/entropies: compress →
    /// decompress must be byte-identical (the K14 round-trip gate at the
    /// blob level).
    #[test]
    fn band_roundtrip_all_dtypes() {
        for dtype in [
            "F32",
            "F16",
            "BF16",
            "F8_E4M3",
            "F8_E5M2", // compat band
            "F64",
            "C64",
            "I8",
            "U8",
            "BOOL",
            "I16",
            "U16",
            "I32",
            "U32",
            "I64",
            "U64",
            "F8_E4M3FNUZ",
            "F8_E5M2FNUZ",
            "F8_E8M0", // Neo band
            "C128",
            "BC32", // codec-level pseudo names (f64/i64-ish payloads below)
        ] {
            for (n, low) in [
                (1usize, true),
                (1000, true),
                (100_000, true),
                (100_000, false),
            ] {
                let scheme = scheme_for_st_dtype(dtype).unwrap();
                // C128/BC32 have no sample() arm — reuse F64/BF16 payloads
                // (the codec only sees bytes + the word geometry)
                let data = match dtype {
                    "C128" => sample("F64", n * 2, low, &[]),
                    "BC32" => sample("BF16", n * 2, low, &[]),
                    _ => sample(dtype, n, low, &[]),
                };
                let elem_bytes = match dtype {
                    "C128" => 16,
                    "BC32" => 4,
                    _ => scheme.bytes_per_elem(),
                };
                let shape = vec![data.len() as u64 / elem_bytes as u64];
                let blob = compress_tensor(&scheme, &data, &shape, 0, None).expect("compress");
                let back = decompress_tensor(&blob, 0, None).expect("decompress");
                assert_eq!(back.data, data, "{dtype} n={n} low={low}");
                assert_eq!(back.st_dtype, dtype);
                assert_eq!(back.shape, shape);
            }
        }
    }

    /// Sub-byte dtypes (F4 = 4 bits, F6 = 6): the blob shape check runs on
    /// BITS (reference semantics) — shape counts nibbles/sextets, the
    /// payload is packed bytes.
    #[test]
    fn sub_byte_dtypes_roundtrip_and_shape_check() {
        for (dtype, bits) in [("F4", 4usize), ("F6_E2M3", 6), ("F6_E3M2", 6)] {
            let scheme = scheme_for_st_dtype(dtype).unwrap();
            assert_eq!(scheme.bits_per_elem, bits);
            // 40 elements: F4 → 20 bytes, F6 → 30 bytes
            let nelem = 40u64;
            let nbytes = (nelem * bits as u64 / 8) as usize;
            let data = sample(dtype, nbytes, true, &[]);
            let blob = compress_tensor(&scheme, &data, &[nelem], 0, None).expect("compress");
            let back = decompress_tensor(&blob, 0, None).expect("decompress");
            assert_eq!(back.data, data, "{dtype}");
            assert_eq!(back.shape, vec![nelem]);
            // a shape that does not end on a byte boundary is refused
            let bad_blob = tensor_header(&scheme, nbytes as u64, &[7]); // 7×4=28 bits
            assert!(dtype == "F4" || true);
            if bits * 7 % 8 != 0 {
                assert!(inspect_tensor(&bad_blob).is_err(), "{dtype} 7 elems");
            }
            // shape × bits ≠ original_len is refused
            let mut lying = blob.clone();
            let packed_at = 32 + 1; // ndims byte of the packed shape
            lying[packed_at + 1] = 2; // width-1 dim value → 2 elements
            assert!(inspect_tensor(&lying).is_err(), "{dtype} lying shape");
        }
    }

    /// The truncation auto-selection: zero byte planes choose the deepest
    /// lossless mode; anything else stays canonical.
    #[test]
    fn select_truncation_picks_the_deepest_lossless_mode() {
        let i32s = scheme_for_st_dtype("I32").unwrap();
        let i16s = scheme_for_st_dtype("I16").unwrap();
        // values < 256 → keep byte0 only → mode 1
        let data: Vec<u8> = (0..1000u32).flat_map(|i| (i % 200).to_le_bytes()).collect();
        assert_eq!(select_truncation(&i32s, &data).byte_reorder, 1);
        // values < 2^16 → mode 9
        let data: Vec<u8> = (0..1000u32)
            .flat_map(|i| (i % 60_000).to_le_bytes())
            .collect();
        assert_eq!(select_truncation(&i32s, &data).byte_reorder, 9);
        // values in [2^16, 2^24) → byte2 non-zero, byte3 zero → mode 41
        let data: Vec<u8> = (0..1000u32)
            .flat_map(|i| (65_536 + i * 16_000).to_le_bytes())
            .collect();
        assert_eq!(select_truncation(&i32s, &data).byte_reorder, 41);
        // values in [2^8, 2^16) → mode 9
        let data: Vec<u8> = (0..1000u32)
            .flat_map(|i| (256 + i * 60).to_le_bytes())
            .collect();
        assert_eq!(select_truncation(&i32s, &data).byte_reorder, 9);
        // full-range values (all four bytes used) → canonical 220
        let data: Vec<u8> = (0..1000u32)
            .flat_map(|i| (0x0100_0000u32.wrapping_add(i.wrapping_mul(0x0101_0101))).to_le_bytes())
            .collect();
        assert_eq!(select_truncation(&i32s, &data).byte_reorder, 220);
        // NEGATIVE i32s have 0xFF top bytes → never truncated
        let data: Vec<u8> = (0..1000i32).flat_map(|i| (-i - 1).to_le_bytes()).collect();
        assert_eq!(select_truncation(&i32s, &data).byte_reorder, 220);
        // i16: values < 256 → mode 1; multiples of 256 → mode 8
        let data: Vec<u8> = (0..1000u32)
            .flat_map(|i| ((i % 200) as u16).to_le_bytes())
            .collect();
        assert_eq!(select_truncation(&i16s, &data).byte_reorder, 1);
        let data: Vec<u8> = (0..1000u32)
            .flat_map(|i| (((i % 200) * 256) as u16).to_le_bytes())
            .collect();
        assert_eq!(select_truncation(&i16s, &data).byte_reorder, 8);
        // all-zero data → the low-keeping mode wins (mode 1)
        let zeros = vec![0u8; 4096];
        assert_eq!(select_truncation(&i32s, &zeros).byte_reorder, 1);
        assert_eq!(select_truncation(&i16s, &zeros).byte_reorder, 1);
        // dtypes without truncation support never change
        for d in ["F32", "BF16", "I64", "U64", "I8", "BOOL", "F64"] {
            let s = scheme_for_st_dtype(d).unwrap();
            let data = vec![0u8; 256 * s.bytes_per_elem().max(1)];
            assert_eq!(
                select_truncation(&s, &data).byte_reorder,
                s.byte_reorder,
                "{d}"
            );
        }
        // empty data → canonical
        assert_eq!(select_truncation(&i32s, &[]).byte_reorder, 220);
    }

    /// End-to-end truncation round-trips through the blob API: the header
    /// carries the chosen mode and the decode restores byte-exactly.
    #[test]
    fn truncated_blobs_roundtrip() {
        let cases: &[(&str, u8, Vec<u8>)] = &[
            (
                "I32",
                9,
                (0..70_000u32)
                    .flat_map(|i| (i % 50_000).to_le_bytes())
                    .collect(),
            ),
            (
                "U16",
                8,
                (0..70_000u32)
                    .flat_map(|i| (((i % 250) * 256) as u16).to_le_bytes())
                    .collect(),
            ),
        ];
        for &(dtype, expected_mode, ref data) in cases {
            let base = scheme_for_st_dtype(dtype).unwrap();
            let scheme = select_truncation(&base, data);
            assert_eq!(scheme.byte_reorder, expected_mode, "{dtype}");
            let shape = vec![data.len() as u64 / base.bytes_per_elem() as u64];
            let blob = compress_tensor(&scheme, data, &shape, 0, None).expect("compress");
            assert_eq!(blob[5], expected_mode, "header byte 5 records the mode");
            let back = decompress_tensor(&blob, 0, None).expect("decompress");
            assert_eq!(&back.data, data, "{dtype} roundtrip");
            // truncation beats the canonical layout on this data
            let full = compress_tensor(&base, data, &shape, 0, None).expect("compress full");
            assert!(
                blob.len() < full.len(),
                "{dtype}: {} vs {}",
                blob.len(),
                full.len()
            );
        }
    }

    /// Band-strict mode gate: compatibility codes accept ONLY their
    /// canonical byte_reorder, Neo integer codes their truncation modes.
    #[test]
    fn mode_gate_is_band_strict() {
        // a bf16 blob claiming truncation mode 1 is refused (official
        // encoders never write it — reinterpretation would be guesswork)
        let scheme = scheme_for_st_dtype("BF16").unwrap();
        let data = sample("BF16", 1000, true, &[]);
        let mut blob = compress_tensor(&scheme, &data, &[1000], 0, None).unwrap();
        assert_eq!(blob[5], 10);
        blob[5] = 1;
        let err = inspect_tensor(&blob).unwrap_err().to_string();
        assert!(err.contains("not valid for dtype code"), "{err}");
        // an f32 blob claiming mode 41 is refused
        let scheme = scheme_for_st_dtype("F32").unwrap();
        let data = sample("F32", 1000, true, &[]);
        let mut blob = compress_tensor(&scheme, &data, &[1000], 0, None).unwrap();
        blob[5] = 41;
        assert!(inspect_tensor(&blob).is_err());
        // an I32 blob claiming mode 8 (a 2-plane mode) is refused
        let scheme = scheme_for_st_dtype("I32").unwrap();
        let data = sample("I32", 1000, false, &[]);
        let mut blob = compress_tensor(&scheme, &data, &[1000], 0, None).unwrap();
        blob[5] = 8;
        assert!(inspect_tensor(&blob).is_err());
        // the legal truncation modes pass the gate
        for mode in [41u8, 9, 1] {
            let mut s = scheme;
            s.byte_reorder = mode;
            let zeros: Vec<u8> = (0..4000u32).flat_map(|i| (i % 200).to_le_bytes()).collect();
            let blob = compress_tensor(&s, &zeros, &[4000], 0, None).unwrap();
            assert_eq!(blob[5], mode);
            inspect_tensor(&blob).unwrap_or_else(|e| panic!("mode {mode}: {e}"));
        }
    }

    /// The FP8 production quirk: byte 14 says 18 (256 KiB) while the payload
    /// is chunked at 128 KiB. A blob built exactly like `zipnn.py` does must
    /// decode through the high-level path (regression for the Phase-1 latent
    /// bug — see codec::decompress_container's erratum note).
    #[test]
    fn fp8_blob_decodes_through_container_helper() {
        let scheme = scheme_for_st_dtype("F8_E4M3").unwrap();
        // > 128 KiB so the chunking actually differs between 128K and 256K
        let data = sample("F8_E4M3", 300_000, true, &[]);
        let blob = compress_tensor(&scheme, &data, &[300_000], 0, None).expect("compress");
        assert_eq!(blob[14], 18, "byte 14 records the UNCLAMPED log2");
        let out = codec::decompress_container(&blob, None).expect("container decode");
        assert_eq!(out, data);
    }

    /// Neo's own 1-plane extension types follow the same clamp contract
    /// (they must — a 256 KiB plane cannot be a huff0 block).
    #[test]
    fn neo_single_plane_types_clamp_like_fp8() {
        for dtype in ["U8", "BOOL", "F8_E4M3FNUZ", "F8_E8M0", "F4"] {
            let scheme = scheme_for_st_dtype(dtype).unwrap();
            assert_eq!(effective_chunk(&scheme), HUF_BLOCKSIZE_MAX, "{dtype}");
            let data = sample(dtype, 300_000, true, &[]);
            let blob = compress_tensor(&scheme, &data, &[300_000], 0, None).expect("compress");
            assert_eq!(blob[14], 18, "{dtype} byte 14");
            let out = codec::decompress_container(&blob, None).expect("container decode");
            assert_eq!(out, data, "{dtype}");
        }
    }

    #[test]
    fn header_bytes_match_production_dumps() {
        // Production header dump (Phase 0, fp8 e4m3 tensor):
        // [90,78, 0,5,4, 10, 1, 1, 2, 0, 0,0,0, 0, 18, 29, len...]
        let scheme = scheme_for_st_dtype("F8_E4M3").unwrap();
        let h = tensor_header(&scheme, 1234, &[7, 8]);
        assert_eq!(&h[..10], &[90, 78, 0, 5, 4, 10, 1, 1, 2, 0]);
        assert_eq!(h[13], 0);
        assert_eq!(h[14], 18);
        assert_eq!(h[15], 29);
        assert_eq!(u64::from_le_bytes(h[16..24].try_into().unwrap()), 1234);
        // packed shape follows: ndims=1? no — [7,8] → ndims=2
        assert_eq!(h[32], 2);
        assert_eq!(&h[33..35], &[1, 7]);
        assert_eq!(&h[35..37], &[1, 8]);
        // bf16 production form: byte5=10, byte6=1, code 6
        let scheme = scheme_for_st_dtype("BF16").unwrap();
        let h = tensor_header(&scheme, 16, &[2, 4]);
        assert_eq!(&h[..10], &[90, 78, 0, 5, 4, 10, 1, 1, 2, 0]);
        assert_eq!(h[15], 6);
        // Phase 4 header forms (Neo band): f64 = code 128, byte5 88, byte6 1
        let scheme = scheme_for_st_dtype("F64").unwrap();
        let h = tensor_header(&scheme, 8000, &[1000]);
        assert_eq!(&h[..10], &[90, 78, 0, 5, 4, 88, 1, 1, 2, 0]);
        assert_eq!(h[15], 128);
        // i32 = code 137, byte5 220, byte6 0
        let scheme = scheme_for_st_dtype("I32").unwrap();
        let h = tensor_header(&scheme, 4000, &[1000]);
        assert_eq!(&h[..10], &[90, 78, 0, 5, 4, 220, 0, 1, 2, 0]);
        assert_eq!(h[15], 137);
        // truncated i32 records the mode
        let mut s = scheme;
        s.byte_reorder = 41;
        let h = tensor_header(&s, 4000, &[1000]);
        assert_eq!(h[5], 41);
        assert_eq!(h[6], 0);
        // c64 = code 130, 4 planes with the f32 reorder
        let scheme = scheme_for_st_dtype("C64").unwrap();
        let h = tensor_header(&scheme, 8000, &[1000]);
        assert_eq!(&h[..10], &[90, 78, 0, 5, 4, 220, 1, 1, 2, 0]);
        assert_eq!(h[15], 130);
        // bool = code 134, single plane
        let scheme = scheme_for_st_dtype("BOOL").unwrap();
        let h = tensor_header(&scheme, 100, &[100]);
        assert_eq!(&h[..10], &[90, 78, 0, 5, 4, 10, 0, 1, 2, 0]);
        assert_eq!(h[15], 134);
    }

    #[test]
    fn torch_dtype_names_and_shapes_match_legacy() {
        assert_eq!(scheme_for_st_dtype("F32").unwrap().torch_name, "float32");
        assert_eq!(scheme_for_st_dtype("BF16").unwrap().torch_name, "bfloat16");
        assert_eq!(
            scheme_for_st_dtype("F8_E4M3").unwrap().torch_name,
            "float8_e4m3fn"
        );
        // Phase 4 names (verified against torch 2.14.0 str() forms)
        assert_eq!(scheme_for_st_dtype("F64").unwrap().torch_name, "float64");
        assert_eq!(scheme_for_st_dtype("C64").unwrap().torch_name, "complex64");
        assert_eq!(scheme_for_st_dtype("BOOL").unwrap().torch_name, "bool");
        assert_eq!(scheme_for_st_dtype("U16").unwrap().torch_name, "uint16");
        assert_eq!(scheme_for_st_dtype("U64").unwrap().torch_name, "uint64");
        assert_eq!(
            scheme_for_st_dtype("F8_E4M3FNUZ").unwrap().torch_name,
            "float8_e4m3fnuz"
        );
        assert_eq!(
            scheme_for_st_dtype("F8_E8M0").unwrap().torch_name,
            "float8_e8m0fnu"
        );
        assert_eq!(
            scheme_for_st_dtype("F4").unwrap().torch_name,
            "float4_e2m1fn_x2"
        );
        // no torch spelling exists for the F6 types — the safetensors name
        assert_eq!(
            scheme_for_st_dtype("F6_E2M3").unwrap().torch_name,
            "F6_E2M3"
        );
        // str(list(shape)) compatibility
        assert_eq!(shape_string(&[1, 2]), "[1, 2]");
        assert_eq!(shape_string(&[]), "[]");
        assert_eq!(shape_string(&[4096, 4096]), "[4096, 4096]");
    }

    #[test]
    fn table_is_consistent_with_the_dtype_module() {
        // every table code resolves in dtype.rs with matching geometry, and
        // the st-name lookup round-trips through the code
        for entry in DTYPE_TABLE {
            let plane = dtype::scheme_for_dtype(entry.code)
                .unwrap_or_else(|e| panic!("code {} missing in dtype.rs: {e}", entry.code));
            let scheme = scheme_for_st_dtype(entry.st).expect("st lookup");
            assert_eq!(scheme.dtype_code, entry.code);
            assert_eq!(scheme.num_planes, plane.num_planes);
            assert_eq!(scheme.bits_per_elem, plane.bits_per_elem);
            assert_eq!(scheme.byte_reorder, plane.canonical_mode());
            let (st, torch) = st_dtype_for_code(entry.code).unwrap();
            assert_eq!(st, entry.st);
            assert_eq!(torch, entry.torch);
        }
        // alias codes decode like their primaries
        assert_eq!(st_dtype_for_code(2).unwrap(), ("F32", "float32"));
        assert_eq!(st_dtype_for_code(5).unwrap(), ("F16", "float16"));
        // unknown codes stay explicit errors
        for code in [0u8, 3, 7, 9, 13, 24, 31, 127, 147, 200, 255] {
            assert!(st_dtype_for_code(code).is_err(), "code {code}");
        }
    }

    #[test]
    fn scalar_and_empty_tensors() {
        let scheme = scheme_for_st_dtype("BF16").unwrap();
        // scalar: 1 element, shape []
        let data = [0x3fu8, 0x80];
        let blob = compress_tensor(&scheme, &data, &[], 0, None).expect("compress");
        let back = decompress_tensor(&blob, 0, None).expect("decompress");
        assert_eq!(back.data, data);
        assert_eq!(back.shape, Vec::<u64>::new());
        // zero-element tensor: the "not worth it" rule (blob >= data) keeps
        // it a pass-through in the pipeline; the blob itself must still work
        let blob = compress_tensor(&scheme, &[], &[0], 0, None).expect("compress");
        let back = decompress_tensor(&blob, 0, None).expect("decompress");
        assert!(back.data.is_empty());
        // Phase 4 types: scalar + empty for an 8-plane and a 1-plane scheme
        for dtype in ["F64", "I64", "BOOL", "F4"] {
            let scheme = scheme_for_st_dtype(dtype).unwrap();
            let blob = compress_tensor(&scheme, &[], &[0], 0, None).expect("compress");
            let back = decompress_tensor(&blob, 0, None).expect("decompress");
            assert!(back.data.is_empty(), "{dtype}");
            if scheme.bits_per_elem % 8 == 0 {
                let one = vec![7u8; scheme.bytes_per_elem()];
                let blob = compress_tensor(&scheme, &one, &[], 0, None).expect("compress");
                let back = decompress_tensor(&blob, 0, None).expect("decompress");
                assert_eq!(back.data, one, "{dtype} scalar");
            }
        }
    }

    /// Plan §4.4.2 allocation-cap: a blob whose header tells a CONSISTENT
    /// lie (shape × elem == original_len == 1 TiB) must be refused by the
    /// cap BEFORE any allocation — an OOM abort would kill ComfyUI itself.
    #[test]
    fn allocation_bomb_is_capped_not_allocated() {
        let scheme = scheme_for_st_dtype("BF16").unwrap();
        let huge: u64 = 1 << 40;
        let mut blob = tensor_header(&scheme, huge, &[huge / 2]);
        blob.extend_from_slice(&[0u8; 64]); // stub payload
        let err = decompress_tensor(&blob, 0, None).unwrap_err();
        assert!(matches!(err, crate::CodecError::Size(_)), "{err:?}");
        let mut out = Vec::new();
        let err = decompress_tensor_into(&blob, &mut out, 0, None, 1 << 20).unwrap_err();
        assert!(matches!(err, crate::CodecError::Size(_)), "{err:?}");
        assert!(out.is_empty(), "nothing allocated");
    }

    #[test]
    fn hostile_blobs_error_not_panic() {
        // truncated header / garbage payload / lying original_len
        let scheme = scheme_for_st_dtype("F32").unwrap();
        let data = sample("F32", 50_000, true, &[]);
        let blob = compress_tensor(&scheme, &data, &[50_000], 0, None).unwrap();
        for cut in [1usize, 10, 31, 32, 33, 40, blob.len() / 2, blob.len() - 1] {
            assert!(
                decompress_tensor(&blob[..cut], 0, None).is_err(),
                "cut {cut}"
            );
        }
        let mut lying = blob.clone();
        // original_len way beyond the payload → capped by max_output=orig_len
        lying[16..24].copy_from_slice(&(1u64 << 40).to_le_bytes());
        assert!(decompress_tensor(&lying, 0, None).is_err());
        // empty input
        assert!(decompress_tensor(&[], 0, None).is_err());
        // random garbage
        let junk: Vec<u8> = (0..1024).map(|i| (i % 251) as u8).collect();
        assert!(decompress_tensor(&junk, 0, None).is_err());
        // Phase 4 surface: the same battery against an f64 blob and a
        // truncated i32 blob (hostile inputs must never panic)
        let scheme = scheme_for_st_dtype("F64").unwrap();
        let data = sample("F64", 30_000, true, &[]);
        let blob = compress_tensor(&scheme, &data, &[30_000], 0, None).unwrap();
        for cut in [1usize, 31, 33, blob.len() / 2, blob.len() - 1] {
            assert!(
                decompress_tensor(&blob[..cut], 0, None).is_err(),
                "f64 cut {cut}"
            );
        }
        let mut lying = blob.clone();
        lying[16..24].copy_from_slice(&(1u64 << 40).to_le_bytes());
        assert!(decompress_tensor(&lying, 0, None).is_err());
        let base = scheme_for_st_dtype("I32").unwrap();
        let data: Vec<u8> = (0..30_000u32)
            .flat_map(|i| (i % 100).to_le_bytes())
            .collect();
        let scheme = select_truncation(&base, &data);
        assert_eq!(scheme.byte_reorder, 1);
        let blob = compress_tensor(&scheme, &data, &[30_000], 0, None).unwrap();
        for cut in [1usize, 31, 33, blob.len() / 2, blob.len() - 1] {
            assert!(
                decompress_tensor(&blob[..cut], 0, None).is_err(),
                "trunc cut {cut}"
            );
        }
        // a truncated blob whose original_len is NOT word-aligned cannot be
        // built by Neo, but a hostile header may claim it → explicit error
        let mut lying = blob.clone();
        lying[16..24].copy_from_slice(&(30_001u64).to_le_bytes());
        assert!(decompress_tensor(&lying, 0, None).is_err());
    }
}
