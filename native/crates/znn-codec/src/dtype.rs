//! dtype code <-> plane scheme tables (Plan §4.6.3: compatibility band +
//! Neo extension band).
//!
//! ## Upstream compatibility band (codes 1–30)
//!
//! The dtypes the vendored `zipnn.py` TORCH dispatch actually implements
//! (codes verified against `third_party/zipnn/util_torch.py ZipNNDtypeEnum`
//! and the compress() dispatch on 2026-09-23; production headers were dumped
//! to confirm the exact (byte_reorder, bit_reorder) pairs written per dtype):
//!
//! | dtype            | code | planes | bit_reorder | byte_reorder | elem |
//! |------------------|------|--------|-------------|--------------|------|
//! | float32 / float  | 1/2  | 4      | 1           | 220          | 4    |
//! | float16 / half   | 4/5  | 2      | 0           | 10           | 2    |
//! | bfloat16         | 6    | 2      | 1           | 10           | 2    |
//! | float8_e4m3fn    | 29   | 1      | 1 (ignored) | 10           | 1    |
//! | float8_e5m2      | 30   | 1      | 1 (ignored) | 10           | 1    |
//!
//! ## Neo extension band (codes 128–255, Phase 4 — Plan §4.6.2/§4.6.3)
//!
//! Codes deliberately far above the upstream enum (which ends at 30), so the
//! official zipnn 0.5.4 decoder can never mistake them for its own: it
//! rejects every unknown code with an explicit `ValueError: Unsupported
//! Dtype N` (demonstrated against the pip build in `scripts/l5` section E —
//! no silent corruption, Plan §4.6.3 failure-mode safety). Files containing
//! extension-band blobs carry the `znn_neo_extended="1"` metadata marker.
//!
//! | dtype (safetensors)      | code | planes | bit_reorder | byte_reorder    | bits |
//! |--------------------------|------|--------|-------------|-----------------|------|
//! | F64                      | 128  | 8      | 1 (f64)     | 88              | 64   |
//! | — complex128 (codec-only)| 129  | 8      | 1 (f64)     | 88              | 128  |
//! | C64 (= 2×f32 words)      | 130  | 4      | 1 (f32)     | 220             | 64   |
//! | — bcomplex32 (codec-only)| 131  | 2      | 1 (bf16)    | 10              | 32   |
//! | I8 / U8 / BOOL           | 132–134 | 1   | 0           | 10              | 8    |
//! | I16 / U16                | 135/136 | 2   | 0           | 10 (+trunc 1/8) | 16   |
//! | I32 / U32                | 137/138 | 4   | 0           | 220 (+trunc 41/9/1) | 32 |
//! | I64 / U64                | 139/140 | 8   | 0           | 88              | 64   |
//! | F8_E4M3FNUZ / F8_E5M2FNUZ| 141/142 | 1  | 0           | 10              | 8    |
//! | F8_E8M0                  | 143  | 1      | 0           | 10              | 8    |
//! | F4                       | 144  | 1      | 0           | 10              | 4    |
//! | F6_E2M3 / F6_E3M2        | 145/146 | 1   | 0           | 10              | 6    |
//!
//! Complex types are word-transformed: C64 is two consecutive f32 words, so
//! the 4-plane f32 reorder applies per u32 exactly as for F32 (Plan §4.6.2
//! "C64 は u32 単位処理で同一変換が成立"); complex128 likewise per u64, and
//! bcomplex32 is one (real, imag) bf16 pair per u32 = the bf16-pair transform.
//! `complex128`/`bcomplex32` have NO safetensors 0.8 representation (verified
//! against the pip package on 2026-09-26: `safetensors.torch.save` raises
//! `KeyError: torch.complex128`), so their codes are codec-level only — the
//! safetensors pipeline refuses to restore such blobs with an explicit error.
//!
//! **C64 band decision (Plan §4.6.3 open question, settled by demonstration
//! 2026-09-26):** the upstream enum reserves code 9 for COMPLEX64, but the
//! official 0.5.4 decoder's dtype dispatch has no arm for it — `decompress_bin`
//! ends in `raise ValueError(f"Unsupported Dtype {self.dtype}")` for 9 exactly
//! like for Neo-band codes (proven against the pip build; L5 section E2 pins
//! it). Writing C64 as code 9 would therefore produce files the official tool
//! rejects anyway, while LOSING the clean band separation — so C64 uses the
//! Neo extension code 130.
//!
//! ## Truncation modes (Neo-clean semantics, extension band only)
//!
//! The C core's truncation modes are dead code (`handle_split_mode_41/9/1`
//! commented out; the dtype16 8/1 paths leave the second plane's container
//! slots uninitialized) and `zipnn.py` never writes them. Neo formalises them
//! (Plan §6.2 Phase 4 "トランケートモード 1/9/41/8 の正式実装"): when whole
//! byte planes of an integer tensor are zero across the ENTIRE tensor (checked
//! by the compressor), those planes are DROPPED from the payload and the mode
//! byte records which planes survive; the decompressor zero-fills the dropped
//! byte positions. The container keeps `numBuf = word size` planes (dropped
//! planes contribute zero-length chunks: chunkType 0, empty cumSizes deltas),
//! so every container-size formula is unchanged.
//!
//! | word | mode | kept planes (byte positions)         | C naming          |
//! |------|------|--------------------------------------|-------------------|
//! | 2    | 10   | {0,1} (none dropped)                 | byte group        |
//! | 2    | 1    | {0} — the LOW byte survives          | "Truncate LSByte"†|
//! | 2    | 8    | {1} — the HIGH byte survives         | "Truncate MSByte"†|
//! | 4    | 220  | {0,1,2,3} (none dropped)             | byte group        |
//! | 4    | 41   | {0,1,2} — drop the MSB               | truncate 1 byte   |
//! | 4    | 9    | {0,1} — drop the two MSBs            | truncate 2 bytes  |
//! | 4    | 1    | {0} — only the LSB survives          | truncate 3 bytes  |
//!
//! † the C comments name modes 8/1 by the byte they OMIT with an inverted
//! little-endian reading; the table above states the actual data flow of
//! `split_bytearray_dtype16`/`combine_buffers_dtype16` (mode 8 keeps
//! `src[i+1]`, the high byte, and refills the low byte with 0).
//!
//! Truncation is LOSSLESS by construction: the compressor verifies the
//! dropped planes are all-zero before choosing a mode. It is offered only
//! for the Neo integer codes (I16/U16/I32/U32 — Plan §4.6.2; I64/U64 rely on
//! the plain 8-plane split, whose top planes are zero-fed to huff0 anyway).
//!
//! ## 8-plane mode byte
//!
//! The 8-plane interleave (F64/complex128/I64/U64) needs a `byte_reorder`
//! value of its own: upstream defines 0/1/8/9/10/41/169/220/255 and never
//! writes anything but 220/10, so Neo claims **88** (mnemonic: 8 planes) —
//! a value no official encoder produces and no official decoder accepts.
//!
//! Delta files use `float32` semantics on raw bytes (`bytearray_dtype=
//! "float32"` → the (4, 1, 220) compatibility path — Plan §4.5-6) and are
//! unaffected by the extension band.
//!
//! Note on FP8 `bit_reorder`: production writes `bit_reorder=1` into the
//! header, but the C core NEVER consumes `bits_mode` when `num_buf == 1`
//! (`split_bytearray_dtype8` does not receive it; combine is a memcpy) — so
//! reorder is a no-op for 1-plane data in both implementations (verified
//! empirically: bits 0/1 produce byte-identical payloads and cross-decode).
//! Neo's own 1-plane extension types write the honest `bit_reorder=0`.

use crate::{CodecError, CodecResult};

// Upstream compatibility band codes (ZipNNDtypeEnum, util_torch.py).
pub const FLOAT32: u8 = 1;
pub const FLOAT: u8 = 2;
pub const FLOAT16: u8 = 4;
pub const HALF: u8 = 5;
pub const BFLOAT16: u8 = 6;
pub const FLOAT8_E4M3FN: u8 = 29;
pub const FLOAT8_E5M2: u8 = 30;

// Neo extension band codes (Plan §4.6.3 — assigned exactly as planned).
pub const NEO_F64: u8 = 128;
pub const NEO_COMPLEX128: u8 = 129;
pub const NEO_COMPLEX64: u8 = 130;
pub const NEO_BCOMPLEX32: u8 = 131;
pub const NEO_I8: u8 = 132;
pub const NEO_U8: u8 = 133;
pub const NEO_BOOL: u8 = 134;
pub const NEO_I16: u8 = 135;
pub const NEO_U16: u8 = 136;
pub const NEO_I32: u8 = 137;
pub const NEO_U32: u8 = 138;
pub const NEO_I64: u8 = 139;
pub const NEO_U64: u8 = 140;
pub const NEO_F8_E4M3FNUZ: u8 = 141;
pub const NEO_F8_E5M2FNUZ: u8 = 142;
pub const NEO_F8_E8M0: u8 = 143;
pub const NEO_F4: u8 = 144;
pub const NEO_F6_E2M3: u8 = 145;
pub const NEO_F6_E3M2: u8 = 146;

/// First code of the Neo extension band (codes ≥ this are Neo-only).
pub const NEO_BAND_START: u8 = 128;

/// byte_reorder mode values (header byte 5).
pub const MODE_4PLANES: u8 = 220; // 8b1_10_11_100 — 4-plane interleave (f32)
pub const MODE_2PLANES: u8 = 10; // 8b01_010   — 2-plane interleave (f16/bf16) and 1-plane copy (fp8)
/// Neo extension: 8-plane interleave (f64/complex128/i64/u64). Value chosen
/// collision-free against every byte_reorder upstream defines or writes
/// (see the module docs).
pub const MODE_8PLANES: u8 = 88;
/// Truncation modes (Neo-clean semantics, extension band only — module docs):
/// keep the low 3 of 4 bytes / low 2 of 4 / low 1 of 4-or-2 / high 1 of 2.
pub const MODE_TRUNC_LOW3_OF4: u8 = 41;
pub const MODE_TRUNC_LOW2_OF4: u8 = 9;
pub const MODE_TRUNC_LOW1: u8 = 1;
pub const MODE_TRUNC_HIGH1_OF2: u8 = 8;

/// Which interoperability band a dtype code belongs to (Plan §4.6.3).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Band {
    /// Codes 1–30: written exactly like upstream zipnn 0.5.4, so official
    /// tools decode these blobs unchanged.
    Compat,
    /// Codes ≥ 128: Neo-only; official tools reject them with an explicit
    /// error. Files with any such blob carry `znn_neo_extended="1"`.
    Neo,
}

/// A per-plane keep/drop mask over the container's `num_planes` planes
/// (entries beyond `num_planes` are always false). Full masks mean "no
/// truncation" — the compatibility-band layout.
pub type PlaneMask = [bool; 8];

/// The plane/reorder scheme a dtype code implies (the decompressor derives
/// `num_buf` from the dtype code exactly like `zipnn.py decompress()` does:
/// default 4, bfloat16/float16 → 2, float8 → 1; the Neo band extends the
/// table with 8-plane and 1-plane integer/MX types).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PlaneScheme {
    /// Number of byte planes in the container (`num_buf` in the C ABI):
    /// 1, 2, 4 or 8 — equal to the transform word size.
    pub num_planes: usize,
    /// Element size in bytes of the transform WORD (for length/divisibility
    /// checks in the codec: chunks must split into whole words when
    /// truncation is active). Equal to `num_planes`.
    pub elem_size: usize,
    /// True bit width of one dtype ELEMENT (F4 = 4, F6 = 6, C64 = 64 — two
    /// f32 words; everything else `elem_size * 8`). The blob shape check is
    /// `nelem × bits_per_elem / 8 == original_len` (the reference safetensors
    /// validation semantics).
    pub bits_per_elem: usize,
    /// Whether the sign/exponent bit reorder is ACTIVE for this dtype
    /// (fp8 records bit_reorder=1 in headers but the reorder is a no-op
    /// because there is a single plane — see module docs).
    pub reorder_active: bool,
    /// Interoperability band of the code.
    pub band: Band,
    /// Additional (truncation) byte_reorder modes this dtype may carry.
    /// Empty for every compatibility-band dtype (their blobs must stay
    /// byte-canonical for official tools) and for Neo types without
    /// truncation support.
    pub trunc_modes: &'static [u8],
}

impl PlaneScheme {
    /// The byte_reorder value Neo writes for a fresh (untruncated) blob of
    /// this scheme.
    #[must_use]
    pub const fn canonical_mode(&self) -> u8 {
        match self.num_planes {
            4 => MODE_4PLANES,
            8 => MODE_8PLANES,
            _ => MODE_2PLANES, // 2-plane and 1-plane both use 10
        }
    }

    /// Whether `byte_reorder` is a legal mode for a blob of this dtype:
    /// the canonical mode plus (Neo integer types only) the truncation
    /// modes. Compatibility-band blobs must carry their canonical mode —
    /// anything else could not have come from an official encoder.
    #[must_use]
    pub fn allows_mode(&self, byte_reorder: u8) -> bool {
        byte_reorder == self.canonical_mode() || self.trunc_modes.contains(&byte_reorder)
    }

    /// True for single-plane schemes (the fp8-style 128 KiB chunk clamp of
    /// `zipnn.py` applies — and is REQUIRED, since a 256 KiB plane would
    /// exceed `HUF_BLOCKSIZE_MAX`).
    #[must_use]
    pub const fn is_single_plane(&self) -> bool {
        self.num_planes == 1
    }
}

const NO_TRUNC: &[u8] = &[];
const TRUNC_16: &[u8] = &[MODE_TRUNC_LOW1, MODE_TRUNC_HIGH1_OF2];
const TRUNC_32: &[u8] = &[MODE_TRUNC_LOW3_OF4, MODE_TRUNC_LOW2_OF4, MODE_TRUNC_LOW1];

fn compat(num_planes: usize, bits: usize, reorder_active: bool) -> PlaneScheme {
    PlaneScheme {
        num_planes,
        elem_size: num_planes,
        bits_per_elem: bits,
        reorder_active,
        band: Band::Compat,
        trunc_modes: NO_TRUNC,
    }
}

fn neo(num_planes: usize, bits: usize, reorder_active: bool, trunc: &'static [u8]) -> PlaneScheme {
    PlaneScheme {
        num_planes,
        elem_size: num_planes,
        bits_per_elem: bits,
        reorder_active,
        band: Band::Neo,
        trunc_modes: trunc,
    }
}

/// The scheme for a dtype code (compatibility band + Neo extension band).
///
/// # Errors
/// Unknown codes are rejected with an explicit message (the official zipnn
/// decoder also refuses unknown codes — no silent corruption; Plan §4.6.3
/// failure-mode safety). Codes in 31..=127 are reserved: upstream may assign
/// them in future versions, and Neo must never pre-empt that space.
pub fn scheme_for_dtype(code: u8) -> CodecResult<PlaneScheme> {
    match code {
        FLOAT32 | FLOAT => Ok(compat(4, 32, true)),
        FLOAT16 | HALF => Ok(compat(2, 16, false)),
        BFLOAT16 => Ok(compat(2, 16, true)),
        FLOAT8_E4M3FN | FLOAT8_E5M2 => Ok(compat(1, 8, false)),
        NEO_F64 => Ok(neo(8, 64, true, NO_TRUNC)),
        NEO_COMPLEX128 => Ok(neo(8, 128, true, NO_TRUNC)),
        NEO_COMPLEX64 => Ok(neo(4, 64, true, NO_TRUNC)),
        NEO_BCOMPLEX32 => Ok(neo(2, 32, true, NO_TRUNC)),
        NEO_I8 | NEO_U8 | NEO_BOOL => Ok(neo(1, 8, false, NO_TRUNC)),
        NEO_I16 | NEO_U16 => Ok(neo(2, 16, false, TRUNC_16)),
        NEO_I32 | NEO_U32 => Ok(neo(4, 32, false, TRUNC_32)),
        NEO_I64 | NEO_U64 => Ok(neo(8, 64, false, NO_TRUNC)),
        NEO_F8_E4M3FNUZ | NEO_F8_E5M2FNUZ | NEO_F8_E8M0 => Ok(neo(1, 8, false, NO_TRUNC)),
        NEO_F4 => Ok(neo(1, 4, false, NO_TRUNC)),
        NEO_F6_E2M3 | NEO_F6_E3M2 => Ok(neo(1, 6, false, NO_TRUNC)),
        // 128..=146 are matched individually above; the REST of the band is
        // unassigned (the arm must not overlap the assigned codes — clippy
        // match_overlapping_arm)
        147..=255 => Err(CodecError::Unsupported(format!(
            "dtype code {code} is an unassigned Neo extension-band code (Plan §4.6.3 assigns 128–146)"
        ))),
        other => Err(CodecError::Unsupported(format!(
            "dtype code {other} is not implemented (the ZipNN 0.5.4 torch path covers 1/2/4/5/6/29/30; upstream-only codes 3,7–28 are dead in the official codec too; Neo extension band starts at {NEO_BAND_START})"
        ))),
    }
}

/// Whether a dtype code belongs to the Neo extension band.
#[must_use]
pub const fn is_neo_code(code: u8) -> bool {
    code >= NEO_BAND_START
}

/// Validate a header's (byte_reorder, num_planes) combination at the CODEC
/// level (dtype-agnostic). Accepts the C core's ratio gates
/// (`buffer_ratio_dtype32`: 220; `buffer_ratio_dtype16`: 10/8/1; `num_buf==1`:
/// 10 via `split_bytearray_dtype8`) PLUS the Neo Phase-4 extensions: the
/// 8-plane mode and the truncation modes. Which of these a given BLOB may
/// actually use is a dtype-level question — [`PlaneScheme::allows_mode`]
/// enforces it where the dtype code is known (compatibility-band blobs stay
/// canonical-only).
///
/// # Errors
/// Any combination outside the table above (`return -1` / `PyErr_SetString`
/// in the C core; explicit Neo errors for the rest).
pub fn validate_mode(byte_reorder: u8, num_planes: usize) -> CodecResult<()> {
    // The mask derivation IS the validation table (single source of truth).
    plane_mask(byte_reorder, num_planes)?;
    Ok(())
}

/// The keep-mask of a (byte_reorder, num_planes) pair: which byte planes of
/// each word are stored in the payload (`false` = dropped by truncation and
/// zero-filled on decode). See the module docs for the mode table.
///
/// # Errors
/// Mode/plane-count combinations outside the table (including any truncation
/// mode for 1- or 8-plane data, and any unknown mode value).
pub fn plane_mask(byte_reorder: u8, num_planes: usize) -> CodecResult<PlaneMask> {
    let mut m = [false; 8];
    let full = |m: &mut PlaneMask, n: usize| {
        for slot in m.iter_mut().take(n) {
            *slot = true;
        }
    };
    match (num_planes, byte_reorder) {
        (1, MODE_2PLANES) => m[0] = true,
        (2, MODE_2PLANES) => full(&mut m, 2),
        (2, MODE_TRUNC_LOW1) => m[0] = true,
        (2, MODE_TRUNC_HIGH1_OF2) => m[1] = true,
        (4, MODE_4PLANES) => full(&mut m, 4),
        (4, MODE_TRUNC_LOW3_OF4) => full(&mut m, 3),
        (4, MODE_TRUNC_LOW2_OF4) => full(&mut m, 2),
        (4, MODE_TRUNC_LOW1) => m[0] = true,
        (8, MODE_8PLANES) => full(&mut m, 8),
        (1 | 2 | 4 | 8, other) => {
            return Err(CodecError::Unsupported(format!(
                "byte_reorder {other} invalid for {num_planes}-plane data (modes: 1-plane 10; 2-plane 10/1/8; 4-plane 220/41/9/1; 8-plane 88 — truncation modes are Neo extension-band only, Plan §4.6.3)"
            )));
        }
        (other, _) => {
            return Err(CodecError::Unsupported(format!(
                "num_planes {other} outside {{1,2,4,8}}"
            )));
        }
    }
    Ok(m)
}

/// True when the mask drops at least one plane (a truncation mode).
#[must_use]
pub fn is_truncated(mask: &PlaneMask, num_planes: usize) -> bool {
    mask.iter().take(num_planes).any(|keep| !keep)
}

/// The number of kept planes of a mask.
#[must_use]
pub fn kept_planes(mask: &PlaneMask, num_planes: usize) -> usize {
    mask.iter().take(num_planes).filter(|k| **k).count()
}

/// Per-plane byte lengths of one chunk under a mask: kept planes get
/// `total / num_planes` (the interleave is uniform), dropped planes get 0.
/// Truncated layouts require the chunk to split into whole words — the
/// caller (codec) enforces `total % num_planes == 0` BEFORE calling.
/// For full masks this is byte-identical to [`crate::planes::plane_sizes`]
/// when `total % num_planes == 0`; the codec keeps using `plane_sizes` on
/// the (dominant) full-mask path so the compatibility-band behaviour —
/// including its C-exact remainder layout — is untouched.
///
/// # Errors
/// A truncated mask over a length that is not a whole number of words.
pub fn masked_plane_sizes(
    total_len: usize,
    num_planes: usize,
    mask: &PlaneMask,
) -> CodecResult<Vec<usize>> {
    if is_truncated(mask, num_planes) {
        if num_planes == 0 || total_len % num_planes != 0 {
            return Err(CodecError::Size(format!(
                "truncated mode requires element-aligned lengths: {total_len} % {num_planes} != 0"
            )));
        }
        let elems = total_len / num_planes;
        Ok((0..num_planes)
            .map(|b| if mask[b] { elems } else { 0 })
            .collect())
    } else {
        Ok(crate::planes::plane_sizes(total_len, num_planes))
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
        // compatibility schemes never truncate and stay canonical-only
        for code in [FLOAT32, FLOAT16, BFLOAT16, FLOAT8_E4M3FN, FLOAT8_E5M2] {
            let s = scheme_for_dtype(code).unwrap();
            assert_eq!(s.band, Band::Compat);
            assert!(s.trunc_modes.is_empty());
            assert!(s.allows_mode(s.canonical_mode()));
        }
    }

    #[test]
    fn neo_band_schemes_match_the_plan_table() {
        // Plan §4.6.3 code assignment, verbatim
        let cases: &[(u8, usize, usize, bool)] = &[
            (NEO_F64, 8, 64, true),
            (NEO_COMPLEX128, 8, 128, true),
            (NEO_COMPLEX64, 4, 64, true),
            (NEO_BCOMPLEX32, 2, 32, true),
            (NEO_I8, 1, 8, false),
            (NEO_U8, 1, 8, false),
            (NEO_BOOL, 1, 8, false),
            (NEO_I16, 2, 16, false),
            (NEO_U16, 2, 16, false),
            (NEO_I32, 4, 32, false),
            (NEO_U32, 4, 32, false),
            (NEO_I64, 8, 64, false),
            (NEO_U64, 8, 64, false),
            (NEO_F8_E4M3FNUZ, 1, 8, false),
            (NEO_F8_E5M2FNUZ, 1, 8, false),
            (NEO_F8_E8M0, 1, 8, false),
            (NEO_F4, 1, 4, false),
            (NEO_F6_E2M3, 1, 6, false),
            (NEO_F6_E3M2, 1, 6, false),
        ];
        for &(code, planes, bits, reorder) in cases {
            let s = scheme_for_dtype(code).unwrap();
            assert_eq!(s.num_planes, planes, "code {code} planes");
            assert_eq!(s.bits_per_elem, bits, "code {code} bits");
            assert_eq!(s.reorder_active, reorder, "code {code} reorder");
            assert_eq!(s.band, Band::Neo, "code {code} band");
            assert!(is_neo_code(code));
            assert!(s.allows_mode(s.canonical_mode()), "code {code} canonical");
        }
        // canonical modes per plane count
        assert_eq!(scheme_for_dtype(NEO_F64).unwrap().canonical_mode(), 88);
        assert_eq!(scheme_for_dtype(NEO_I32).unwrap().canonical_mode(), 220);
        assert_eq!(scheme_for_dtype(NEO_I16).unwrap().canonical_mode(), 10);
        assert_eq!(scheme_for_dtype(NEO_BOOL).unwrap().canonical_mode(), 10);
        // truncation is offered exactly for I16/U16 and I32/U32
        for code in [NEO_I16, NEO_U16] {
            let s = scheme_for_dtype(code).unwrap();
            assert!(s.allows_mode(1) && s.allows_mode(8) && !s.allows_mode(41));
        }
        for code in [NEO_I32, NEO_U32] {
            let s = scheme_for_dtype(code).unwrap();
            assert!(s.allows_mode(41) && s.allows_mode(9) && s.allows_mode(1));
            assert!(!s.allows_mode(8), "8 is a 2-plane mode");
        }
        for code in [
            NEO_F64,
            NEO_I64,
            NEO_U64,
            NEO_COMPLEX64,
            NEO_BCOMPLEX32,
            NEO_BOOL,
        ] {
            let s = scheme_for_dtype(code).unwrap();
            assert!(s.trunc_modes.is_empty(), "code {code} must not truncate");
        }
        // compatibility codes are never "neo"
        assert!(!is_neo_code(FLOAT32) && !is_neo_code(FLOAT8_E5M2));
    }

    #[test]
    fn unknown_and_reserved_codes_are_explicit_errors() {
        for code in [0u8, 3, 7, 9, 13, 24, 31, 100, 127] {
            assert!(scheme_for_dtype(code).is_err(), "code {code}");
        }
        // the code-9 (COMPLEX64) rejection is the demonstrated settlement of
        // the Plan §4.6.3 band question: upstream reserved the code but its
        // decoder raises — Neo uses 130 (module docs, L5 section E2)
        let err = scheme_for_dtype(9).unwrap_err().to_string();
        assert!(err.contains("not implemented"), "{err}");
        // unassigned extension-band codes stay rejected
        for code in [147u8, 200, 255] {
            let err = scheme_for_dtype(code).unwrap_err().to_string();
            assert!(err.contains("unassigned"), "{err}");
        }
    }

    #[test]
    fn mode_validation_matches_the_gates() {
        // compatibility combinations (unchanged from Phase 1)
        assert!(validate_mode(MODE_4PLANES, 4).is_ok());
        assert!(validate_mode(MODE_2PLANES, 2).is_ok());
        assert!(validate_mode(MODE_2PLANES, 1).is_ok());
        assert!(validate_mode(MODE_2PLANES, 4).is_err());
        assert!(validate_mode(MODE_4PLANES, 2).is_err());
        assert!(validate_mode(255, 4).is_err());
        // Neo Phase-4 combinations
        assert!(validate_mode(MODE_8PLANES, 8).is_ok());
        assert!(validate_mode(MODE_8PLANES, 4).is_err());
        assert!(validate_mode(88, 2).is_err());
        assert!(validate_mode(1, 2).is_ok()); // truncate-to-low (Neo I16)
        assert!(validate_mode(8, 2).is_ok()); // truncate-to-high (Neo I16)
        assert!(validate_mode(8, 4).is_err());
        assert!(validate_mode(41, 4).is_ok());
        assert!(validate_mode(9, 4).is_ok());
        assert!(validate_mode(1, 4).is_ok());
        assert!(validate_mode(41, 2).is_err());
        assert!(validate_mode(1, 1).is_err());
        assert!(validate_mode(10, 3).is_err());
        assert!(validate_mode(10, 8).is_err());
    }

    #[test]
    fn plane_masks() {
        assert_eq!(
            plane_mask(MODE_2PLANES, 2).unwrap(),
            [true, true, false, false, false, false, false, false]
        );
        assert_eq!(plane_mask(MODE_TRUNC_LOW1, 2).unwrap()[..2], [true, false]);
        assert_eq!(
            plane_mask(MODE_TRUNC_HIGH1_OF2, 2).unwrap()[..2],
            [false, true]
        );
        assert_eq!(
            plane_mask(MODE_TRUNC_LOW3_OF4, 4).unwrap()[..4],
            [true, true, true, false]
        );
        assert_eq!(
            plane_mask(MODE_TRUNC_LOW2_OF4, 4).unwrap()[..4],
            [true, true, false, false]
        );
        assert_eq!(
            plane_mask(MODE_TRUNC_LOW1, 4).unwrap()[..4],
            [true, false, false, false]
        );
        let m8 = plane_mask(MODE_8PLANES, 8).unwrap();
        assert!(m8.iter().all(|k| *k));
        assert!(!is_truncated(&m8, 8));
        assert_eq!(kept_planes(&m8, 8), 8);
        let m41 = plane_mask(MODE_TRUNC_LOW3_OF4, 4).unwrap();
        assert!(is_truncated(&m41, 4));
        assert_eq!(kept_planes(&m41, 4), 3);
    }

    #[test]
    fn masked_sizes() {
        let m = plane_mask(MODE_TRUNC_LOW2_OF4, 4).unwrap();
        assert_eq!(
            masked_plane_sizes(1024, 4, &m).unwrap(),
            vec![256, 256, 0, 0]
        );
        // truncated layouts refuse non-word-aligned lengths
        assert!(masked_plane_sizes(1025, 4, &m).is_err());
        // full masks delegate to the C-exact plane_sizes (remainders allowed)
        let full = plane_mask(MODE_4PLANES, 4).unwrap();
        assert_eq!(masked_plane_sizes(5, 4, &full).unwrap(), vec![2, 1, 1, 1]);
        assert_eq!(masked_plane_sizes(0, 4, &full).unwrap(), vec![0, 0, 0, 0]);
    }
}
