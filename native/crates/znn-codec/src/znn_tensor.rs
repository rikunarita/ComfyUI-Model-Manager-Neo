//! Per-tensor ZipNN blobs — the container semantics the official
//! `zipnn_compress_safetensors.py` / Neo's legacy `py/compress.py` apply to
//! every floating-point tensor of a safetensors file (Plan §4.5, Appendix B).
//!
//! A compressed tensor is stored as a 1-D `U8` vector holding one COMPLETE
//! ZN container: `[32-byte header][packed shape][codec payload]`, built with
//! `input_format = TORCH` and the ORIGINAL tensor's dtype code + shape — so
//! the official `zipnn_safetensors()` loaders and scripts can decode Neo's
//! files unchanged (Plan §4.6.3 compatibility band).
//!
//! Parameter mapping (verified against `third_party/zipnn/zipnn.py`
//! `compress_torch_numpy_byte` / `decompress_bin` and production header
//! dumps, 2026-09-24):
//!
//! | safetensors dtype | code | torch name        | planes | bit_reorder | byte_reorder | chunk        |
//! |-------------------|------|-------------------|--------|-------------|--------------|--------------|
//! | F32               | 1    | float32           | 4      | 1           | 220          | 256 KiB      |
//! | F16               | 4    | float16           | 2      | 0           | 10           | 256 KiB      |
//! | BF16              | 6    | bfloat16          | 2      | 1           | 10           | 256 KiB      |
//! | F8_E4M3           | 29   | float8_e4m3fn     | 1      | 1 (ignored) | 10           | **128 KiB**  |
//! | F8_E5M2           | 30   | float8_e5m2       | 1      | 1 (ignored) | 10           | **128 KiB**  |
//!
//! The FP8 chunk quirk: `zipnn.py` always writes `compression_chunk_log2=18`
//! into byte 14 but passes `min(128 KiB, chunk)` to the C core when
//! `num_buf == 1` (`HUF_BLOCKSIZE_MAX` bound) — both the compressor and the
//! decompressor must apply the clamp, never the raw header value.
//!
//! Everything else (F64, C64, integers, BOOL, MX types, …) is PASSED THROUGH
//! untouched in Phase 2, exactly like the legacy pipeline passes non-float
//! tensors; the legacy path actually RAISES on f64/complex models (its
//! dispatch falls through to `ValueError`) while Neo stores them verbatim —
//! strictly more capable, same format. Compression of the Neo extension band
//! is Phase 4.

use std::sync::atomic::AtomicBool;

use crate::codec::{self, CoreParams};
use crate::header::{InputFormat, ZnHeader, pack_shape};
use crate::{CodecError, CodecResult, HUF_BLOCKSIZE_MAX};

/// ZipNN container version Neo writes (0.5.4 — the vendored/upstream
/// generation; `zipnn.py _version_major/minor/tiny`).
pub const ZNN_VERSION: [u8; 3] = [0, 5, 4];

/// The compression-band scheme for one safetensors dtype string.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TensorScheme {
    /// Header byte 15 dtype code (upstream compatibility band).
    pub dtype_code: u8,
    /// torch dtype name recorded in `znn_compressed_vectors`
    /// (`str(tensor.dtype)` without the `torch.` prefix).
    pub torch_name: &'static str,
    /// Plane count (`num_buf`).
    pub num_planes: usize,
    /// Header byte 6 (`bits_mode`).
    pub bit_reorder: u8,
    /// Header byte 5 (`bytes_mode`).
    pub byte_reorder: u8,
    /// Element size in bytes.
    pub elem_size: usize,
}

/// The scheme for a COMPRESSIBLE compatibility-band safetensors dtype
/// (f32/f16/bf16/fp8×2); `None` for everything that passes through
/// untouched in Phase 2.
#[must_use]
pub fn scheme_for_st_dtype(st_dtype: &str) -> Option<TensorScheme> {
    Some(match st_dtype {
        "F32" => TensorScheme {
            dtype_code: 1,
            torch_name: "float32",
            num_planes: 4,
            bit_reorder: 1,
            byte_reorder: 220,
            elem_size: 4,
        },
        "F16" => TensorScheme {
            dtype_code: 4,
            torch_name: "float16",
            num_planes: 2,
            bit_reorder: 0,
            byte_reorder: 10,
            elem_size: 2,
        },
        "BF16" => TensorScheme {
            dtype_code: 6,
            torch_name: "bfloat16",
            num_planes: 2,
            bit_reorder: 1,
            byte_reorder: 10,
            elem_size: 2,
        },
        "F8_E4M3" => TensorScheme {
            dtype_code: 29,
            torch_name: "float8_e4m3fn",
            num_planes: 1,
            bit_reorder: 1,
            byte_reorder: 10,
            elem_size: 1,
        },
        "F8_E5M2" => TensorScheme {
            dtype_code: 30,
            torch_name: "float8_e5m2",
            num_planes: 1,
            bit_reorder: 1,
            byte_reorder: 10,
            elem_size: 1,
        },
        _ => return None,
    })
}

/// The safetensors dtype string + torch name for a header dtype CODE (the
/// decompression direction; accepts the alias codes 2=FLOAT and 5=HALF the
/// way `zipnn.py decompress_bin` does).
///
/// # Errors
/// Codes outside the compatibility band (Phase 4 Neo-extension codes are
/// rejected with an explicit "not implemented" message).
pub fn st_dtype_for_code(code: u8) -> CodecResult<(&'static str, &'static str)> {
    Ok(match code {
        1 | 2 => ("F32", "float32"),
        4 | 5 => ("F16", "float16"),
        6 => ("BF16", "bfloat16"),
        29 => ("F8_E4M3", "float8_e4m3fn"),
        30 => ("F8_E5M2", "float8_e5m2"),
        128..=255 => {
            return Err(CodecError::Unsupported(format!(
                "dtype code {code} is a Neo extension-band type (Phase 4) — this file needs a newer Neo"
            )));
        }
        other => {
            return Err(CodecError::Unsupported(format!(
                "dtype code {other} is not produced by the ZipNN 0.5.4 torch path (Phase 4 territory)"
            )));
        }
    })
}

/// The effective codec chunk for a scheme: the production 256 KiB, clamped
/// to `HUF_BLOCKSIZE_MAX` for single-plane (fp8) data — the `zipnn.py`
/// quirk documented in the module header.
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

/// Build the 32-byte header + packed shape prefix of one tensor blob
/// (TORCH input format, the original dtype code, byte 14 = log2 of the
/// UNCLAMPED configured chunk — production quirk: fp8 blobs also carry 18).
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
    /// safetensors dtype string of the ORIGINAL tensor (e.g. `"BF16"`).
    pub st_dtype: &'static str,
    /// torch dtype name as recorded in `znn_compressed_vectors`.
    pub torch_name: &'static str,
    /// Shape from the blob's packed header.
    pub shape: Vec<u64>,
    /// Restored payload length in bytes (the header's `original_len`).
    pub len: u64,
}

/// The effective decode chunk of a blob header — zipnn.py's fp8 clamp
/// (`compression_chunk if num_buf != 1 else min(128K, compression_chunk)`).
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
/// Everything [`decompress_tensor`] reports about the header/shape.
pub fn inspect_tensor(blob: &[u8]) -> CodecResult<RestoredInfo> {
    let (header, shape, _used) = ZnHeader::parse(blob)?;
    let (st_dtype, torch_name) = st_dtype_for_code(header.dtype_code)?;
    let scheme = scheme_for_st_dtype(st_dtype)
        .ok_or_else(|| CodecError::Unsupported(format!("internal: no scheme for {st_dtype}")))?;
    // run the chunk derivation too — it is part of the decode contract and
    // must not fail later than the plan
    let _chunk = blob_chunk(&header, scheme.num_planes)?;
    let nelem = shape
        .iter()
        .try_fold(1u64, |a, &d| a.checked_mul(d))
        .ok_or_else(|| CodecError::Shape("shape product overflows".to_owned()))?;
    let expect = nelem
        .checked_mul(scheme.elem_size as u64)
        .ok_or_else(|| CodecError::Shape("tensor size overflows".to_owned()))?;
    if expect != header.original_len {
        return Err(CodecError::Shape(format!(
            "packed shape {shape:?} × {} bytes implies {expect} but the header declares original_len {}",
            scheme.elem_size, header.original_len
        )));
    }
    Ok(RestoredInfo {
        st_dtype,
        torch_name,
        shape,
        len: header.original_len,
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
/// scheme, FP8 chunk clamp) plus the hostile-input guards of the codec.
///
/// # Errors
/// Invalid/hostile blobs (header, shape, payload), unsupported dtype codes
/// (Phase 4), delta/streaming containers (Phase 3), and an `original_len`
/// inconsistent with the packed shape.
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
    let scheme = scheme_for_st_dtype(info.st_dtype).ok_or_else(|| {
        CodecError::Unsupported(format!("internal: no scheme for {}", info.st_dtype))
    })?;
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

    fn sample(dtype: &str, n: usize, low_entropy: bool, shape: &[u64]) -> Vec<u8> {
        let scheme = scheme_for_st_dtype(dtype).expect("band dtype");
        let mut data = Vec::with_capacity(n * scheme.elem_size);
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
                _ => {
                    let b: u8 = if low_entropy {
                        (0x38 | ((x >> 12) & 0x7)) as u8
                    } else {
                        ((x >> 16) & 0x7F) as u8
                    };
                    data.push(b);
                }
            }
            let _ = i;
        }
        let _ = shape;
        data
    }

    #[test]
    fn band_roundtrip_all_dtypes() {
        for dtype in ["F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"] {
            for (n, low) in [
                (1usize, true),
                (1000, true),
                (100_000, true),
                (100_000, false),
            ] {
                let scheme = scheme_for_st_dtype(dtype).unwrap();
                let data = sample(dtype, n, low, &[]);
                let shape = vec![data.len() as u64 / scheme.elem_size as u64];
                let blob = compress_tensor(&scheme, &data, &shape, 0, None).expect("compress");
                let back = decompress_tensor(&blob, 0, None).expect("decompress");
                assert_eq!(back.data, data, "{dtype} n={n} low={low}");
                assert_eq!(back.st_dtype, dtype);
                assert_eq!(back.shape, shape);
            }
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
    }

    #[test]
    fn torch_dtype_names_and_shapes_match_legacy() {
        assert_eq!(scheme_for_st_dtype("F32").unwrap().torch_name, "float32");
        assert_eq!(scheme_for_st_dtype("BF16").unwrap().torch_name, "bfloat16");
        assert_eq!(
            scheme_for_st_dtype("F8_E4M3").unwrap().torch_name,
            "float8_e4m3fn"
        );
        // str(list(shape)) compatibility
        assert_eq!(shape_string(&[1, 2]), "[1, 2]");
        assert_eq!(shape_string(&[]), "[]");
        assert_eq!(shape_string(&[4096, 4096]), "[4096, 4096]");
    }

    #[test]
    fn passthrough_dtypes_have_no_scheme() {
        for d in ["F64", "C64", "I64", "U8", "BOOL", "I32", "F8_E8M0", "F4"] {
            assert!(scheme_for_st_dtype(d).is_none(), "{d} passes through");
        }
        // and their codes are explicit errors on the decode side
        assert!(st_dtype_for_code(3).is_err()); // FLOAT64
        assert!(st_dtype_for_code(9).is_err()); // COMPLEX64
        assert!(st_dtype_for_code(128).is_err()); // Neo band
        // alias codes decode like their primaries
        assert_eq!(st_dtype_for_code(2).unwrap(), ("F32", "float32"));
        assert_eq!(st_dtype_for_code(5).unwrap(), ("F16", "float16"));
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
    }
}
