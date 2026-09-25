//! Sign/exponent bit reordering — the ZipNN pre-transform that groups the
//! sign bit next to the exponent so plane 0 becomes low-entropy
//! (Plan §4.5-1, §4.6.2).
//!
//! Word transforms are verbatim ports of the vendored C reference
//! (`third_party/zipnn-core/csrc/data_manipulation_dtype32.c`
//! `reorder_float_bits_dtype32` / `revert_float_bits_dtype32` and
//! `data_manipulation_dtype16.c` `reorder_float_bits_dtype16` /
//! `revert_float_bits_dtype16`), re-read 2026-09-23:
//!
//! * f32 (u32 LE word):  `sign=(u>>8)&0x0080_0000; exp=(u<<1)&0xFF00_0000;
//!   man=u&0x007F_FFFF;  u' = exp|sign|man`   → layout `[exp8][sign][man23]`
//! * bf16 pair (u32 LE holding two bf16):
//!   `sign=(u>>8)&0x0080_0080; exp=(u<<1)&0xFF00_FF00; man=u&0x007F_007F`
//! * f64 (u64 LE word, Neo's new Phase-4 scheme — the exact f32
//!   generalisation): `sign=(u>>11)&0x0010_0000_0000_0000;
//!   exp=(u<<1)&0xFFE0_0000_0000_0000; man=u&0x000F_FFFF_FFFF_FFFF`
//!   → layout `[exp11 bits 63..53][sign bit 52][man52 bits 51..0]`.
//!
//!   **Plan §4.6.2 erratum (found by this implementation, 2026-09-23):** the
//!   plan's f64 formula (`sign=(u>>12)&0x0008…`, `man=u&0x0007_FFFF…`) is NOT
//!   a bijection — it drops mantissa bit 51 into the sign slot and leaves
//!   bit 52 dead, so ~50% of all u64 patterns fail to round-trip (empirically
//!   100,045/200,000 random failures; e.g. 1.5 → 1.0). The corrected
//!   constants below keep the full 52-bit mantissa and place the sign at
//!   bit 52, directly below the exponent — the literal f32 pattern
//!   (`[exp][sign][man]`) generalised to 11/1/52 bits. The proptest
//!   `f64_reorder_is_a_bijection` (any::<u64>) pins this permanently.
//!
//! The reverts are the exact inverses (C `revert_*`, verified by proptest).
//!
//! Buffer-level application mirrors the C `reorder_all_floats_*`: operate on
//! whole words (`len/4` u32s or `len/8` u64s); trailing bytes of a partial
//! word are left UNTOUCHED (they are still plane-interleaved by `planes`).
//! Unlike the C core — which destroys its input in place (the reason Neo's
//! Python layer clones tensors) — the Rust codec applies these transforms
//! while copying (Plan §4.3): the input slice is never mutated.

/// Which word transform a payload uses.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ReorderKind {
    /// No transform (f16, fp8, integer planes).
    #[default]
    None,
    /// f32 / c64-as-u32 (4-plane, `bit_reorder=1`).
    F32,
    /// bf16 pairs packed in u32 (2-plane, `bit_reorder=1`).
    Bf16,
    /// f64 / complex128-as-u64 (8-plane, Phase 4).
    F64,
}

/// f32 sign/exponent reorder (C `reorder_float_bits_dtype32`).
#[inline]
#[must_use]
pub const fn reorder_f32_word(u: u32) -> u32 {
    let sign = (u >> 8) & 0x0080_0000;
    let exponent = (u << 1) & 0xFF00_0000;
    let mantissa = u & 0x007F_FFFF;
    exponent | sign | mantissa
}

/// Inverse of [`reorder_f32_word`] (C `revert_float_bits_dtype32`).
#[inline]
#[must_use]
pub const fn revert_f32_word(u: u32) -> u32 {
    let sign = (u << 8) & 0x8000_0000;
    let exponent = (u >> 1) & 0x7F80_0000;
    let mantissa = u & 0x007F_FFFF;
    sign | exponent | mantissa
}

/// bf16-pair sign/exponent reorder (C `reorder_float_bits_dtype16`):
/// a u32 holds two little-endian bf16 values; both halves transform alike.
#[inline]
#[must_use]
pub const fn reorder_bf16_pair(u: u32) -> u32 {
    let sign = (u >> 8) & 0x0080_0080;
    let exponent = (u << 1) & 0xFF00_FF00;
    let mantissa = u & 0x007F_007F;
    exponent | sign | mantissa
}

/// Inverse of [`reorder_bf16_pair`] (C `revert_float_bits_dtype16`).
#[inline]
#[must_use]
pub const fn revert_bf16_pair(u: u32) -> u32 {
    let sign = (u << 8) & 0x8000_8000;
    let exponent = (u >> 1) & 0x7F80_7F80;
    let mantissa = u & 0x007F_007F;
    sign | exponent | mantissa
}

/// f64 sign/exponent reorder — Neo's new scheme (corrected Plan §4.6.2, see
/// the module erratum): exponent bits 62..52 move to 63..53, the sign (bit
/// 63) lands at bit 52 directly below the exponent, and the FULL 52-bit
/// mantissa keeps bits 51..0. Bijection (pinned by proptest over any u64).
#[inline]
#[must_use]
pub const fn reorder_f64_word(u: u64) -> u64 {
    let sign = (u >> 11) & 0x0010_0000_0000_0000;
    let exponent = (u << 1) & 0xFFE0_0000_0000_0000;
    let mantissa = u & 0x000F_FFFF_FFFF_FFFF;
    exponent | sign | mantissa
}

/// Inverse of [`reorder_f64_word`].
#[inline]
#[must_use]
pub const fn revert_f64_word(u: u64) -> u64 {
    let sign = (u << 11) & 0x8000_0000_0000_0000;
    let exponent = (u >> 1) & 0x7FF0_0000_0000_0000;
    let mantissa = u & 0x000F_FFFF_FFFF_FFFF;
    sign | exponent | mantissa
}

/// Apply the reorder to every whole word of `buf` (u32 words for
/// [`ReorderKind::F32`]/[`ReorderKind::Bf16`], u64 for [`ReorderKind::F64`]);
/// the trailing partial word is left untouched (C semantics).
pub fn reorder_in_place(kind: ReorderKind, buf: &mut [u8]) {
    transform_in_place(kind, buf, true);
}

/// Apply the inverse of [`reorder_in_place`].
pub fn revert_in_place(kind: ReorderKind, buf: &mut [u8]) {
    transform_in_place(kind, buf, false);
}

fn transform_in_place(kind: ReorderKind, buf: &mut [u8], forward: bool) {
    match kind {
        ReorderKind::None => {}
        ReorderKind::F32 | ReorderKind::Bf16 => {
            for w in buf.chunks_exact_mut(4) {
                let u = u32::from_le_bytes(w.try_into().expect("4 bytes"));
                let t = match (kind, forward) {
                    (ReorderKind::F32, true) => reorder_f32_word(u),
                    (ReorderKind::F32, false) => revert_f32_word(u),
                    (ReorderKind::Bf16, true) => reorder_bf16_pair(u),
                    (ReorderKind::Bf16, false) => revert_bf16_pair(u),
                    _ => u, // unreachable: F64/None handled elsewhere
                };
                w.copy_from_slice(&t.to_le_bytes());
            }
        }
        ReorderKind::F64 => {
            for w in buf.chunks_exact_mut(8) {
                let u = u64::from_le_bytes(w.try_into().expect("8 bytes"));
                let t = if forward {
                    reorder_f64_word(u)
                } else {
                    revert_f64_word(u)
                };
                w.copy_from_slice(&t.to_le_bytes());
            }
        }
    }
}

/// The transform a (bit_reorder, plane count) header pair implies — mirroring
/// the C core, where `bits_mode` is only consumed by the 2/4-plane paths:
/// 1-plane data is NEVER reordered regardless of the header bit (fp8 headers
/// carry bit_reorder=1; the C core ignores it — verified byte-identical
/// payloads for bits 0/1, see dtype.rs module docs).
#[must_use]
pub const fn kind_for(bit_reorder: u8, num_planes: usize, is_f64_scheme: bool) -> ReorderKind {
    if bit_reorder != 1 || num_planes == 1 {
        ReorderKind::None
    } else if is_f64_scheme {
        ReorderKind::F64
    } else if num_planes == 4 {
        ReorderKind::F32
    } else {
        ReorderKind::Bf16
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn f32_word_layout_is_exp_sign_mantissa() {
        // -1.0f32 = 0xBF800000: sign=1, exp=0x7F(127), man=0.
        // Reordered layout [exp8 bits 31..24][sign bit 23][man23 bits 22..0]:
        // the exp PATTERN 0111_1111 moves from bits 30..23 to 31..24, so the
        // top byte reads 0x7F; the sign lands at bit 23.
        let u = (-1.0f32).to_bits();
        let r = reorder_f32_word(u);
        assert_eq!(r, 0x7F80_0000);
        assert_eq!(r >> 24, 0x7F);
        assert_eq!((r >> 23) & 1, 1, "sign directly below exponent");
        assert_eq!(r & 0x7F_FFFF, 0);
        assert_eq!(revert_f32_word(r), u);
        // smallest normal (exp=1, positive): pattern 0000_0001 → top byte 0x01
        let u = 1.175_494_4e-38f32.to_bits();
        let r = reorder_f32_word(u);
        assert_eq!(r, 0x0100_0000);
        assert_eq!((r >> 23) & 1, 0);
        assert_eq!(revert_f32_word(r), u);
        // -1.5 keeps its mantissa below the sign slot
        let u = (-1.5f32).to_bits();
        let r = reorder_f32_word(u);
        assert_eq!(r, 0x7FC0_0000);
        assert_eq!(revert_f32_word(r), u);
    }

    #[test]
    fn bf16_pair_transforms_both_halves() {
        // two bf16 packed little-endian: low = -1.0 (0xBF80: sign 1, exp
        // 0x7F, man 0), high = 0.5 (0x3F00: sign 0, exp 0x7E, man 0).
        // Per half: [exp8 bits 15..8][sign bit 7][man7 bits 6..0].
        let u = u32::from(0x3F00u16) << 16 | u32::from(0xBF80u16);
        let r = reorder_bf16_pair(u);
        assert_eq!(r & 0xFFFF, 0x7F80, "low: exp pattern 0x7F, sign bit set");
        assert_eq!(r >> 16, 0x7E00, "high: exp pattern 0x7E, positive");
        assert_eq!(revert_bf16_pair(r), u);
        // mantissa preservation: low = 1.5 bf16 (0x3FC0: exp 0x7F, man 0x40)
        let u2 = u32::from(0x3FC0u16);
        let r2 = reorder_bf16_pair(u2);
        assert_eq!(r2 & 0xFFFF, 0x7F40, "exp 0x7F, sign 0, man 0x40");
        assert_eq!(revert_bf16_pair(r2), u2);
    }

    #[test]
    fn f64_word_layout_and_samples() {
        // -1.0f64: sign=1, exp=0x3FF, man=0 → reordered: exp<<1 top bits,
        // sign at bit 52, mantissa zero.
        let u = (-1.0f64).to_bits();
        let r = reorder_f64_word(u);
        // layout [exp11 bits 63..53][sign bit 52][man52 bits 51..0]: the exp
        // PATTERN 011_1111_1111 (0x3FF) moves to bits 63..53.
        assert_eq!(r, 0x7FF0_0000_0000_0000);
        assert_eq!(r >> 53, 0x3FF, "exponent pattern at bits 63..53");
        assert_eq!((r >> 52) & 1, 1, "sign directly below the exponent");
        assert_eq!(r & 0x000F_FFFF_FFFF_FFFF, 0);
        assert_eq!(revert_f64_word(r), u);
        for v in [
            0.0f64,
            -0.0,
            1.0,
            1.5, // mantissa bit 51 set — the case the uncorrected plan
            // formula corrupts (1.5 → 1.0); must round-trip exactly
            f64::MIN_POSITIVE,
            f64::MAX,
            12.345_678_901_234_567,
            -98.765_432_109_876_54,
        ] {
            let u = v.to_bits();
            assert_eq!(revert_f64_word(reorder_f64_word(u)), u, "value {v}");
        }
        assert_eq!(
            f64::from_bits(revert_f64_word(reorder_f64_word(1.5f64.to_bits()))),
            1.5
        );
    }

    #[test]
    fn in_place_matches_word_semantics_and_preserves_tail() {
        let mut buf: Vec<u8> = (0..13u8).collect(); // 3 u32 words + 1 tail byte
        let orig = buf.clone();
        reorder_in_place(ReorderKind::F32, &mut buf);
        for i in 0..3 {
            let u = u32::from_le_bytes(orig[i * 4..i * 4 + 4].try_into().unwrap());
            assert_eq!(
                u32::from_le_bytes(buf[i * 4..i * 4 + 4].try_into().unwrap()),
                reorder_f32_word(u)
            );
        }
        assert_eq!(buf[12], orig[12], "tail byte untouched");
        revert_in_place(ReorderKind::F32, &mut buf);
        assert_eq!(buf, orig);

        let mut buf64: Vec<u8> = (0..19u8).collect(); // 2 u64 words + 3 tail
        let orig64 = buf64.clone();
        reorder_in_place(ReorderKind::F64, &mut buf64);
        assert_eq!(&buf64[16..], &orig64[16..]);
        revert_in_place(ReorderKind::F64, &mut buf64);
        assert_eq!(buf64, orig64);

        let mut n = vec![1u8, 2, 3];
        reorder_in_place(ReorderKind::None, &mut n);
        assert_eq!(n, [1, 2, 3]);
    }

    #[test]
    fn kind_for_matches_c_consumption_rules() {
        assert_eq!(kind_for(1, 4, false), ReorderKind::F32);
        assert_eq!(kind_for(1, 2, false), ReorderKind::Bf16);
        assert_eq!(kind_for(0, 2, false), ReorderKind::None); // f16
        assert_eq!(kind_for(1, 1, false), ReorderKind::None); // fp8: bits ignored
        assert_eq!(kind_for(1, 8, true), ReorderKind::F64);
        assert_eq!(kind_for(0, 8, true), ReorderKind::None);
    }
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        /// Every transform is a bijection with its revert as the exact
        /// inverse — "全単射" (Plan §6.2 Phase 1: proptest 全単射).
        #[test]
        fn f32_reorder_is_a_bijection(u in any::<u32>()) {
            prop_assert_eq!(revert_f32_word(reorder_f32_word(u)), u);
            prop_assert_eq!(reorder_f32_word(revert_f32_word(u)), u);
        }

        #[test]
        fn bf16_reorder_is_a_bijection(u in any::<u32>()) {
            prop_assert_eq!(revert_bf16_pair(reorder_bf16_pair(u)), u);
            prop_assert_eq!(reorder_bf16_pair(revert_bf16_pair(u)), u);
        }

        #[test]
        fn f64_reorder_is_a_bijection(u in any::<u64>()) {
            prop_assert_eq!(revert_f64_word(reorder_f64_word(u)), u);
            prop_assert_eq!(reorder_f64_word(revert_f64_word(u)), u);
        }

        /// Buffer-level round trip for arbitrary (odd) lengths: the tail of a
        /// partial word must survive untouched.
        #[test]
        fn buffer_roundtrip_any_len(bytes in proptest::collection::vec(any::<u8>(), 0..600)) {
            for kind in [ReorderKind::F32, ReorderKind::Bf16, ReorderKind::F64, ReorderKind::None] {
                let mut buf = bytes.clone();
                reorder_in_place(kind, &mut buf);
                revert_in_place(kind, &mut buf);
                prop_assert_eq!(&buf, &bytes);
            }
        }

        /// Distinct inputs map to distinct outputs (injectivity via inverse).
        #[test]
        fn distinct_words_stay_distinct(a in any::<u32>(), b in any::<u32>()) {
            if a != b {
                prop_assert_ne!(reorder_f32_word(a), reorder_f32_word(b));
                prop_assert_ne!(reorder_bf16_pair(a), reorder_bf16_pair(b));
            }
        }
    }
}
