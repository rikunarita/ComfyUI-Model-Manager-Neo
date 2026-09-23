//! dtype code <-> plane scheme tables (Plan §4.6.3, compatibility band).
//!
//! Phase 1 covers the UPSTREAM-COMPATIBLE band only — the dtypes the vendored
//! `zipnn.py` TORCH dispatch actually implements (codes verified against
//! `third_party/zipnn/util_torch.py ZipNNDtypeEnum` and the compress()
//! dispatch on 2026-09-23; production headers were dumped to confirm the
//! exact (byte_reorder, bit_reorder) pairs written per dtype):
//!
//! | dtype            | code | planes | bit_reorder | byte_reorder | elem |
//! |------------------|------|--------|-------------|--------------|------|
//! | float32 / float  | 1/2  | 4      | 1           | 220          | 4    |
//! | float16 / half   | 4/5  | 2      | 0           | 10           | 2    |
//! | bfloat16         | 6    | 2      | 1           | 10           | 2    |
//! | float8_e4m3fn    | 29   | 1      | 1 (ignored) | 10           | 1    |
//! | float8_e5m2      | 30   | 1      | 1 (ignored) | 10           | 1    |
//!
//! The Neo extension band (codes 128–255: f64 8-plane, integers, MX types)
//! is Phase 4. Delta files use `float32` semantics on raw bytes
//! (`bytearray_dtype="float32"` → code path (4, 1, 220) — see Plan §4.5-6).
//!
//! Note on FP8 `bit_reorder`: production writes `bit_reorder=1` into the
//! header, but the C core NEVER consumes `bits_mode` when `num_buf == 1`
//! (`split_bytearray_dtype8` does not receive it; combine is a memcpy) — so
//! reorder is a no-op for 1-plane data in both implementations (verified
//! empirically: bits 0/1 produce byte-identical payloads and cross-decode).

use crate::{CodecError, CodecResult};

// Upstream compatibility band codes (ZipNNDtypeEnum, util_torch.py).
pub const FLOAT32: u8 = 1;
pub const FLOAT: u8 = 2;
pub const FLOAT16: u8 = 4;
pub const HALF: u8 = 5;
pub const BFLOAT16: u8 = 6;
pub const FLOAT8_E4M3FN: u8 = 29;
pub const FLOAT8_E5M2: u8 = 30;

/// byte_reorder mode values (header byte 5).
pub const MODE_4PLANES: u8 = 220; // 8b1_10_11_100 — 4-plane interleave (f32)
pub const MODE_2PLANES: u8 = 10; // 8b01_010   — 2-plane interleave (f16/bf16) and 1-plane copy (fp8)

/// The plane/reorder scheme a dtype code implies (the decompressor derives
/// `num_buf` from the dtype code exactly like `zipnn.py decompress()` does:
/// default 4, bfloat16/float16 → 2, float8 → 1).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PlaneScheme {
    /// Number of byte planes (`num_buf` in the C ABI): 1, 2 or 4.
    pub num_planes: usize,
    /// Element size in bytes (for shape/length sanity checks).
    pub elem_size: usize,
    /// Whether the sign/exponent bit reorder is ACTIVE for this dtype
    /// (fp8 records bit_reorder=1 in headers but the reorder is a no-op
    /// because there is a single plane — see module docs).
    pub reorder_active: bool,
}

/// The scheme for a compatibility-band dtype code.
///
/// # Errors
/// Unknown / Phase-4 codes are rejected with an explicit message (the
/// official zipnn decoder also refuses unknown codes — no silent corruption;
/// Plan §4.6.3 failure-mode safety).
pub fn scheme_for_dtype(code: u8) -> CodecResult<PlaneScheme> {
    match code {
        FLOAT32 | FLOAT => Ok(PlaneScheme {
            num_planes: 4,
            elem_size: 4,
            reorder_active: true,
        }),
        FLOAT16 | HALF => Ok(PlaneScheme {
            num_planes: 2,
            elem_size: 2,
            reorder_active: false,
        }),
        BFLOAT16 => Ok(PlaneScheme {
            num_planes: 2,
            elem_size: 2,
            reorder_active: true,
        }),
        FLOAT8_E4M3FN | FLOAT8_E5M2 => Ok(PlaneScheme {
            num_planes: 1,
            elem_size: 1,
            reorder_active: false,
        }),
        128..=255 => Err(CodecError::Unsupported(format!(
            "dtype code {code} is a Neo extension-band type (Plan §4.6.3) — implemented in Phase 4"
        ))),
        other => Err(CodecError::Unsupported(format!(
            "dtype code {other} is not implemented by the ZipNN 0.5.4 torch path (integer/complex/f64 codes are Phase 4)"
        ))),
    }
}

/// Validate a header's (byte_reorder, num_planes) combination the way the C
/// core's ratio gates do (`buffer_ratio_dtype32`: only 220;
/// `buffer_ratio_dtype16`: only 10/8/1 — Phase 1 uses 10; `num_buf==1`:
/// only 10 via `split_bytearray_dtype8`).
///
/// # Errors
/// Any combination the vendored C core would reject (`return -1` /
/// `PyErr_SetString`).
pub fn validate_mode(byte_reorder: u8, num_planes: usize) -> CodecResult<()> {
    match num_planes {
        1 => {
            if byte_reorder == MODE_2PLANES {
                Ok(())
            } else {
                Err(CodecError::Unsupported(format!(
                    "byte_reorder {byte_reorder} invalid for 1-plane (fp8) data (C: split_bytearray_dtype8 accepts only 10)"
                )))
            }
        }
        2 => {
            if byte_reorder == MODE_2PLANES {
                Ok(())
            } else {
                // Modes 8/1 (uint16 truncation) are Phase 4.
                Err(CodecError::Unsupported(format!(
                    "byte_reorder {byte_reorder} not supported for 2-plane data in Phase 1 (only 10; truncation modes 8/1 are Phase 4)"
                )))
            }
        }
        4 => {
            if byte_reorder == MODE_4PLANES {
                Ok(())
            } else {
                Err(CodecError::Unsupported(format!(
                    "byte_reorder {byte_reorder} not supported for 4-plane data (C: buffer_ratio_dtype32 accepts only 220; truncation modes 41/9/1 are Phase 4)"
                )))
            }
        }
        other => Err(CodecError::Unsupported(format!(
            "num_planes {other} outside {{1,2,4}} (8-plane f64 is Phase 4)"
        ))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compat_band_schemes() {
        assert_eq!(scheme_for_dtype(FLOAT32).unwrap().num_planes, 4);
        assert_eq!(scheme_for_dtype(FLOAT).unwrap().num_planes, 4);
        assert_eq!(scheme_for_dtype(FLOAT16).unwrap().num_planes, 2);
        assert!(!scheme_for_dtype(FLOAT16).unwrap().reorder_active);
        assert_eq!(scheme_for_dtype(BFLOAT16).unwrap().num_planes, 2);
        assert!(scheme_for_dtype(BFLOAT16).unwrap().reorder_active);
        assert_eq!(scheme_for_dtype(FLOAT8_E4M3FN).unwrap().num_planes, 1);
        assert_eq!(scheme_for_dtype(FLOAT8_E5M2).unwrap().elem_size, 1);
    }

    #[test]
    fn unknown_and_extension_codes_are_explicit_errors() {
        for code in [0u8, 3, 7, 9, 13, 24, 31, 127] {
            assert!(scheme_for_dtype(code).is_err(), "code {code}");
        }
        for code in [128u8, 130, 200, 255] {
            let err = scheme_for_dtype(code).unwrap_err().to_string();
            assert!(err.contains("Phase 4"), "{err}");
        }
    }

    #[test]
    fn mode_validation_matches_the_c_gates() {
        assert!(validate_mode(MODE_4PLANES, 4).is_ok());
        assert!(validate_mode(MODE_2PLANES, 2).is_ok());
        assert!(validate_mode(MODE_2PLANES, 1).is_ok());
        assert!(validate_mode(MODE_2PLANES, 4).is_err());
        assert!(validate_mode(MODE_4PLANES, 2).is_err());
        assert!(validate_mode(1, 2).is_err()); // truncation = Phase 4
        assert!(validate_mode(10, 3).is_err());
        assert!(validate_mode(255, 4).is_err());
    }
}
