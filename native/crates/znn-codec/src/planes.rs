//! N-plane split/join — the ZipNN "byte grouping" pre-transform
//! (Plan §4.5-2, Appendix C.4).
//!
//! The vendored C core (`data_manipulation_dtype16/32.c`) splits a chunk into
//! N byte planes so that like-significant bytes land together before huff0.
//! Its remainder handling is BROKEN: for a final chunk shorter than N bytes
//! it writes through NULL plane pointers (deterministic SEGFAULT for
//! `total % 256 KiB ∈ {1,2,3}` on the 4-plane path — Plan Appendix C), and
//! for other non-divisible lengths it performs 1–3 byte heap-overflow writes
//! plus up to 3 bytes of out-of-bounds reads (UB, silently absorbed by
//! allocator slack).
//!
//! This module implements the CLEAN semantics that Appendix C.4-3 proves
//! interoperable: the bytes the C `combine_*` functions actually read back
//! are exactly the pure N-way interleave with plane sizes
//! `q + (b < total % N)` (q = total / N). So a bounds-checked interleave is
//! **byte-identical to the C in-bounds layout** in both directions:
//! * Rust split → C combine: C reads only the in-bounds bytes (verified by
//!   the L2 differential suite, `scripts/l2/`);
//! * C split → Rust join: same layout (the C overflow garbage lives past the
//!   plane lengths and is never referenced).
//!
//! Reordering (sign/exponent bit transform) is FUSED into the split: the C
//! core reorders the chunk in place before splitting — the Rust codec never
//! mutates its input (Plan §4.3), it transforms words while copying. The
//! trailing partial word (total % 4 bytes) is NOT reordered in either
//! implementation (C `reorder_all_floats_*` processes only len/4 words).
//!
//! The hot loops process fixed-size blocks through `array_chunks` so LLVM
//! emits the same SIMD shuffles gcc produces for the C's byte loops —
//! plane split/join is memcpy-bound work and must run at memcpy speed
//! (Phase 1 speed gate: 速度同等以上).
//!
//! Every Appendix-C crash length is a permanent regression test here
//! (`appendix_c_*`): split/join must succeed, round-trip, and never trap.

use crate::reorder::{ReorderKind, revert_bf16_pair, revert_f32_word, revert_in_place};
use crate::{CodecError, CodecResult};

/// The in-bounds plane sizes of the C layout: `q + (b < total % n)`.
///
/// This single formula is authoritative for BOTH sides: the C compressor's
/// `bufLens` (`handle_split_mode_220`, `split_bytearray_dtype16`) and the C
/// decompressor's per-chunk `decompLen` (`py_combine_dtype`: last chunk =
/// `lastTotal/n` with the first `lastTotal%n` planes getting +1).
#[must_use]
pub fn plane_sizes(total_len: usize, num_planes: usize) -> Vec<usize> {
    let q = total_len / num_planes.max(1);
    let rem = total_len % num_planes.max(1);
    (0..num_planes).map(|b| q + usize::from(b < rem)).collect()
}

/// Split `src` into `num_planes` byte planes (pure interleave), applying the
/// word reorder while copying. `planes[b]` must have exactly
/// `plane_sizes(src.len(), num_planes)[b]` bytes.
///
/// # Errors
/// Plane count outside {1,2,4}, mismatched plane lengths, F64 kind (the
/// 8-plane path is Phase 4).
pub fn split(src: &[u8], planes: &mut [&mut [u8]], kind: ReorderKind) -> CodecResult<()> {
    let total = src.len();
    let n = planes.len();
    if !matches!(n, 1 | 2 | 4) {
        return Err(CodecError::Unsupported(format!(
            "plane count {n} outside {{1,2,4}} (8-plane f64 is Phase 4)"
        )));
    }
    if kind == ReorderKind::F64 {
        return Err(CodecError::Unsupported(
            "F64 reorder belongs to the 8-plane path (Phase 4); planes supports None/F32/Bf16"
                .to_owned(),
        ));
    }
    let expect = plane_sizes(total, n);
    for (b, p) in planes.iter().enumerate() {
        if p.len() != expect[b] {
            return Err(CodecError::Size(format!(
                "plane {b} is {} bytes, layout requires {}",
                p.len(),
                expect[b]
            )));
        }
    }
    match n {
        1 => planes[0].copy_from_slice(src), // kind ignored (C dtype8 path)
        2 => split2(src, planes, kind),
        _ => split4(src, planes, kind),
    }
    Ok(())
}

/// The word transform for a kind (single place so every path — block,
/// scalar remainder, split4 — applies the identical mapping).
#[inline]
fn transform_word(kind: ReorderKind, u: u32) -> u32 {
    match kind {
        ReorderKind::F32 => crate::reorder::reorder_f32_word(u),
        ReorderKind::Bf16 => crate::reorder::reorder_bf16_pair(u),
        ReorderKind::None | ReorderKind::F64 => u,
    }
}

/// 2-plane interleave (even bytes → plane 0, odd → plane 1) with the fused
/// word reorder; the trailing partial word is NOT reordered (C
/// `reorder_all_floats_dtype16` processes len/4 words only).
fn split2(src: &[u8], planes: &mut [&mut [u8]], kind: ReorderKind) {
    let total = src.len();
    let (first, rest) = planes.split_at_mut(1);
    let (p0, p1) = (&mut first[0][..], &mut rest[0][..]);

    // 16-byte blocks: 8 pairs per iteration via array chunks (LLVM emits
    // pshufb-style unpacks for the constant-index shuffles; with the Bf16
    // kind the four u32 transforms SLP-vectorize the same way gcc
    // vectorizes the C's separate reorder pass).
    let pairs = total / 2;
    // 16-byte source blocks (8 pairs → 8+8 plane bytes). A 32-byte variant
    // was tried and measured SLOWER (1698/1274 vs 2055/2021 MB/s): the wider
    // shuffle needs cross-lane packing that LLVM emits poorly — 16B is the
    // sweet spot (two pshufb-class ops per store).
    let n8 = pairs / 8;
    for (s, (e, o)) in src[..n8 * 16].chunks_exact(16).zip(
        p0[..n8 * 8]
            .chunks_exact_mut(8)
            .zip(p1[..n8 * 8].chunks_exact_mut(8)),
    ) {
        let s: &[u8; 16] = s.try_into().expect("16 bytes");
        let t = if kind == ReorderKind::None {
            *s
        } else {
            let mut t = [0u8; 16];
            for k in 0..4 {
                let u = u32::from_le_bytes([s[k * 4], s[k * 4 + 1], s[k * 4 + 2], s[k * 4 + 3]]);
                t[k * 4..k * 4 + 4].copy_from_slice(&transform_word(kind, u).to_le_bytes());
            }
            t
        };
        let e: &mut [u8; 8] = e.try_into().expect("8 bytes");
        let o: &mut [u8; 8] = o.try_into().expect("8 bytes");
        *e = [t[0], t[2], t[4], t[6], t[8], t[10], t[12], t[14]];
        *o = [t[1], t[3], t[5], t[7], t[9], t[11], t[13], t[15]];
    }
    // scalar remainder pairs + odd tail byte
    let word_bytes = (total / 4) * 4;
    for i in n8 * 8..pairs {
        let j = i * 2;
        let b = if kind != ReorderKind::None && j + 1 < word_bytes {
            // pair lies inside a whole word → the word transform applies
            let w = (j / 4) * 4;
            let u = u32::from_le_bytes([src[w], src[w + 1], src[w + 2], src[w + 3]]);
            let t = transform_word(kind, u).to_le_bytes();
            [t[j % 4], t[j % 4 + 1]]
        } else {
            [src[j], src[j + 1]]
        };
        p0[i] = b[0];
        p1[i] = b[1];
    }
    if total % 2 == 1 {
        p0[pairs] = src[total - 1]; // leftover byte → plane 0 (C layout)
    }
}

/// 4-plane interleave (byte k of every word → plane k) with the fused f32
/// sign/exponent reorder; tail bytes go to planes 0..rem untransformed.
fn split4(src: &[u8], planes: &mut [&mut [u8]], kind: ReorderKind) {
    let total = src.len();
    let (first3, last) = planes.split_at_mut(3); // [p0,p1,p2] | [p3]
    let (first2, mid) = first3.split_at_mut(2); // [p0,p1] | [p2]
    let (a, b) = first2.split_at_mut(1); // [p0] | [p1]
    let (p0, p1, p2, p3) = (
        &mut a[0][..],
        &mut b[0][..],
        &mut mid[0][..],
        &mut last[0][..],
    );

    let words = total / 4;
    let n4 = words / 4; // 16-byte blocks = 4 words
    for (s, ((q0, q1), (q2, q3))) in src[..n4 * 16].chunks_exact(16).zip(
        p0[..n4 * 4]
            .chunks_exact_mut(4)
            .zip(p1[..n4 * 4].chunks_exact_mut(4))
            .zip(
                p2[..n4 * 4]
                    .chunks_exact_mut(4)
                    .zip(p3[..n4 * 4].chunks_exact_mut(4)),
            ),
    ) {
        let s: &[u8; 16] = s.try_into().expect("16 bytes");
        // transform the four words (SLP-vectorizable), then transpose bytes
        let mut t = [0u8; 16];
        for k in 0..4 {
            let u = u32::from_le_bytes([s[k * 4], s[k * 4 + 1], s[k * 4 + 2], s[k * 4 + 3]]);
            t[k * 4..k * 4 + 4].copy_from_slice(&transform_word(kind, u).to_le_bytes());
        }
        let q0: &mut [u8; 4] = q0.try_into().expect("4");
        let q1: &mut [u8; 4] = q1.try_into().expect("4");
        let q2: &mut [u8; 4] = q2.try_into().expect("4");
        let q3: &mut [u8; 4] = q3.try_into().expect("4");
        *q0 = [t[0], t[4], t[8], t[12]];
        *q1 = [t[1], t[5], t[9], t[13]];
        *q2 = [t[2], t[6], t[10], t[14]];
        *q3 = [t[3], t[7], t[11], t[15]];
    }
    // scalar remainder words
    for i in n4 * 4..words {
        let u = u32::from_le_bytes(src[i * 4..i * 4 + 4].try_into().expect("4 bytes"));
        let b = transform_word(kind, u).to_le_bytes();
        p0[i] = b[0];
        p1[i] = b[1];
        p2[i] = b[2];
        p3[i] = b[3];
    }
    // tail bytes (total % 4): NOT reordered (C semantics), plane k gets the
    // k-th tail byte at index `words`
    for k in 0..total % 4 {
        let j = words * 4 + k;
        match k {
            0 => p0[words] = src[j],
            1 => p1[words] = src[j],
            2 => p2[words] = src[j],
            _ => {}
        }
    }
}

/// Join `num_planes` planes back into `dst` (exact inverse of [`split`]):
/// interleave, then revert the word reorder over the whole output (C
/// `combine_buffers_*`: interleave, then `revert_all_floats_*(dst, total)` —
/// which touches only the whole words, tail bytes stay as interleaved).
/// The production kinds (F32 with 4 planes, Bf16 with 2) fuse the revert
/// into the interleave loop (one pass instead of two).
///
/// # Errors
/// Plane count outside {1,2,4}, plane/dst length mismatch, F64 kind.
pub fn join(planes: &[&[u8]], dst: &mut [u8], kind: ReorderKind) -> CodecResult<()> {
    let n = planes.len();
    if !matches!(n, 1 | 2 | 4) {
        return Err(CodecError::Unsupported(format!(
            "plane count {n} outside {{1,2,4}} (8-plane f64 is Phase 4)"
        )));
    }
    if kind == ReorderKind::F64 {
        return Err(CodecError::Unsupported(
            "F64 reorder belongs to the 8-plane path (Phase 4); planes supports None/F32/Bf16"
                .to_owned(),
        ));
    }
    let total: usize = planes.iter().map(|p| p.len()).sum();
    if dst.len() != total {
        return Err(CodecError::Size(format!(
            "dst is {} bytes but planes total {total}",
            dst.len()
        )));
    }
    let expect = plane_sizes(total, n);
    for (b, p) in planes.iter().enumerate() {
        if p.len() != expect[b] {
            return Err(CodecError::Size(format!(
                "plane {b} is {} bytes, layout for total {total} requires {}",
                p.len(),
                expect[b]
            )));
        }
    }
    match n {
        1 => {
            dst.copy_from_slice(planes[0]); // kind ignored (C memcpy path)
            return Ok(());
        }
        2 => {
            let (p0, p1) = (planes[0], planes[1]);
            let pairs = p1.len();
            let n8 = pairs / 8;
            if kind == ReorderKind::Bf16 {
                // FUSED interleave + revert per u32 word (identical result
                // to the C's two passes)
                for (d, (a, b)) in dst[..n8 * 16].chunks_exact_mut(16).zip(
                    p0[..n8 * 8]
                        .chunks_exact(8)
                        .zip(p1[..n8 * 8].chunks_exact(8)),
                ) {
                    let a: &[u8; 8] = a.try_into().expect("8");
                    let b: &[u8; 8] = b.try_into().expect("8");
                    let d: &mut [u8; 16] = d.try_into().expect("16");
                    let mut t = [0u8; 16];
                    for k in 0..4 {
                        let u =
                            u32::from_le_bytes([a[k * 2], b[k * 2], a[k * 2 + 1], b[k * 2 + 1]]);
                        t[k * 4..k * 4 + 4].copy_from_slice(&revert_bf16_pair(u).to_le_bytes());
                    }
                    *d = t;
                }
                // scalar remainder WORDS (each word = 2 pairs; the tail
                // bytes past words*4 are handled below, un-reverted)
                let words = total / 4;
                for w in n8 * 4..words {
                    let u =
                        u32::from_le_bytes([p0[w * 2], p1[w * 2], p0[w * 2 + 1], p1[w * 2 + 1]]);
                    dst[w * 4..w * 4 + 4].copy_from_slice(&revert_bf16_pair(u).to_le_bytes());
                }
                // tail bytes (total % 4): raw interleave, never reverted
                for k in 0..total % 4 {
                    let j = words * 4 + k;
                    dst[j] = if k % 2 == 0 { p0[j / 2] } else { p1[j / 2] };
                }
                return Ok(());
            }
            for (d, (a, b)) in dst[..n8 * 16].chunks_exact_mut(16).zip(
                p0[..n8 * 8]
                    .chunks_exact(8)
                    .zip(p1[..n8 * 8].chunks_exact(8)),
            ) {
                let a: &[u8; 8] = a.try_into().expect("8");
                let b: &[u8; 8] = b.try_into().expect("8");
                let d: &mut [u8; 16] = d.try_into().expect("16");
                *d = [
                    a[0], b[0], a[1], b[1], a[2], b[2], a[3], b[3], a[4], b[4], a[5], b[5], a[6],
                    b[6], a[7], b[7],
                ];
            }
            for i in n8 * 8..pairs {
                dst[i * 2] = p0[i];
                dst[i * 2 + 1] = p1[i];
            }
            if p0.len() > pairs {
                // odd total: the leftover byte is the last of plane 0
                dst[2 * pairs] = p0[pairs];
            }
        }
        _ => {
            let (p0, p1, p2, p3) = (planes[0], planes[1], planes[2], planes[3]);
            let q = p3.len(); // the shortest plane = total/4
            let n4 = q / 4;
            if kind == ReorderKind::F32 {
                // FUSED interleave + revert per u32 word (single pass; tail
                // bytes stay un-reverted exactly like the C two-pass form)
                for (d, ((x0, x1), (x2, x3))) in dst[..n4 * 16].chunks_exact_mut(16).zip(
                    p0[..n4 * 4]
                        .chunks_exact(4)
                        .zip(p1[..n4 * 4].chunks_exact(4))
                        .zip(
                            p2[..n4 * 4]
                                .chunks_exact(4)
                                .zip(p3[..n4 * 4].chunks_exact(4)),
                        ),
                ) {
                    let x0: &[u8; 4] = x0.try_into().expect("4");
                    let x1: &[u8; 4] = x1.try_into().expect("4");
                    let x2: &[u8; 4] = x2.try_into().expect("4");
                    let x3: &[u8; 4] = x3.try_into().expect("4");
                    let d: &mut [u8; 16] = d.try_into().expect("16");
                    let mut t = [0u8; 16];
                    for k in 0..4 {
                        let u = u32::from_le_bytes([x0[k], x1[k], x2[k], x3[k]]);
                        t[k * 4..k * 4 + 4].copy_from_slice(&revert_f32_word(u).to_le_bytes());
                    }
                    *d = t;
                }
                for i in n4 * 4..q {
                    let u = u32::from_le_bytes([p0[i], p1[i], p2[i], p3[i]]);
                    dst[i * 4..i * 4 + 4].copy_from_slice(&revert_f32_word(u).to_le_bytes());
                }
                let rem = total % 4;
                for b in 0..rem {
                    dst[q * 4 + b] = planes[b][expect[b] - 1];
                }
                return Ok(());
            }
            for (d, ((x0, x1), (x2, x3))) in dst[..n4 * 16].chunks_exact_mut(16).zip(
                p0[..n4 * 4]
                    .chunks_exact(4)
                    .zip(p1[..n4 * 4].chunks_exact(4))
                    .zip(
                        p2[..n4 * 4]
                            .chunks_exact(4)
                            .zip(p3[..n4 * 4].chunks_exact(4)),
                    ),
            ) {
                let x0: &[u8; 4] = x0.try_into().expect("4");
                let x1: &[u8; 4] = x1.try_into().expect("4");
                let x2: &[u8; 4] = x2.try_into().expect("4");
                let x3: &[u8; 4] = x3.try_into().expect("4");
                let d: &mut [u8; 16] = d.try_into().expect("16");
                *d = [
                    x0[0], x1[0], x2[0], x3[0], x0[1], x1[1], x2[1], x3[1], x0[2], x1[2], x2[2],
                    x3[2], x0[3], x1[3], x2[3], x3[3],
                ];
            }
            for i in n4 * 4..q {
                dst[i * 4] = p0[i];
                dst[i * 4 + 1] = p1[i];
                dst[i * 4 + 2] = p2[i];
                dst[i * 4 + 3] = p3[i];
            }
            // remainder: planes b < total%4 contribute their last byte
            let rem = total % 4;
            for b in 0..rem {
                dst[q * 4 + b] = planes[b][expect[b] - 1];
            }
        }
    }
    // Generic (non-fused) paths: revert over whole words only — exactly the
    // C `revert_all_floats_*` semantics (chunks_exact ignores the tail).
    revert_in_place(kind, dst);
    Ok(())
}

/// Extract a SINGLE plane `b` of the `n`-plane layout of `src` into `dst`
/// (identical bytes to `split(src, planes, kind)`'s `planes[b]`, including
/// the fused word reorder). Used by the codec's "virtual raw plane" path:
/// planes the C heuristics deem incompressible never need a materialised
/// scratch copy — the assembly phase extracts them straight from the source
/// into the output (byte-identical results, one full copy less).
///
/// # Errors
/// Plane index/count outside the {1,2,4} layout, `dst` length mismatch,
/// F64 kind (Phase 4).
pub fn extract_plane(
    src: &[u8],
    n: usize,
    b: usize,
    kind: ReorderKind,
    dst: &mut [u8],
) -> CodecResult<()> {
    if !matches!(n, 1 | 2 | 4) || b >= n {
        return Err(CodecError::Unsupported(format!(
            "extract_plane: n={n} b={b} outside the {{1,2,4}} layout"
        )));
    }
    if kind == ReorderKind::F64 {
        return Err(CodecError::Unsupported(
            "F64 reorder belongs to the 8-plane path (Phase 4)".to_owned(),
        ));
    }
    let total = src.len();
    let expect = plane_sizes(total, n);
    if dst.len() != expect[b] {
        return Err(CodecError::Size(format!(
            "extract_plane: dst {} bytes, layout requires {}",
            dst.len(),
            expect[b]
        )));
    }
    match n {
        1 => dst.copy_from_slice(src), // kind ignored (C dtype8 path)
        2 => {
            // even bytes → plane 0, odd → plane 1 (bf16 reorder fused per word)
            let words = total / 4;
            let mut wi = 0usize; // dst word-pair cursor (2 bytes per word per plane)
            if kind == ReorderKind::None {
                for w in src[..words * 4].chunks_exact(4) {
                    dst[wi] = w[b];
                    dst[wi + 1] = w[b + 2];
                    wi += 2;
                }
            } else {
                for w in src[..words * 4].chunks_exact(4) {
                    let u = u32::from_le_bytes(w.try_into().expect("4 bytes"));
                    let t = transform_word(kind, u).to_le_bytes();
                    dst[wi] = t[b];
                    dst[wi + 1] = t[b + 2];
                    wi += 2;
                }
            }
            // tail bytes (total % 4): raw interleave, plane k gets byte k
            for k in 0..total % 4 {
                if k % 2 == b {
                    let j = words * 4 + k;
                    dst[j / 2] = src[j];
                }
            }
        }
        _ => {
            // byte k of every (reordered) word → plane k; tail byte k → plane k
            let words = total / 4;
            if kind == ReorderKind::None {
                for (i, w) in src[..words * 4].chunks_exact(4).enumerate() {
                    dst[i] = w[b];
                }
            } else {
                for (i, w) in src[..words * 4].chunks_exact(4).enumerate() {
                    let u = u32::from_le_bytes(w.try_into().expect("4 bytes"));
                    dst[i] = transform_word(kind, u).to_le_bytes()[b];
                }
            }
            if b < total % 4 {
                dst[words] = src[words * 4 + b];
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn roundtrip(total: usize, n: usize, kind: ReorderKind, seed: u8) {
        let src: Vec<u8> = (0..total)
            .map(|i| (i as u8).wrapping_mul(seed).wrapping_add(7))
            .collect();
        let sizes = plane_sizes(total, n);
        let mut storage: Vec<Vec<u8>> = sizes.iter().map(|&s| vec![0u8; s]).collect();
        {
            let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
            split(&src, &mut planes, kind).expect("split");
        }
        let mut dst = vec![0u8; total];
        {
            let planes: Vec<&[u8]> = storage.iter().map(|v| v.as_slice()).collect();
            join(&planes, &mut dst, kind).expect("join");
        }
        assert_eq!(dst, src, "total={total} n={n} kind={kind:?} seed={seed}");
    }

    #[test]
    fn roundtrip_exhaustive_small_lengths() {
        // Plan §6.2: "チャンク長 1–8 を含む端数網羅" — exhaustively 0..=72.
        for total in 0..=72usize {
            for n in [1usize, 2, 4] {
                for kind in [ReorderKind::None, ReorderKind::F32, ReorderKind::Bf16] {
                    roundtrip(total, n, kind, 31);
                }
            }
        }
    }

    #[test]
    fn roundtrip_chunk_boundaries() {
        const CHUNK: usize = 262_144;
        for delta in [0usize, 1, 2, 3, 4, 7, 8, 100] {
            for total in [CHUNK - delta, CHUNK + delta, 2 * CHUNK + delta] {
                roundtrip(total, 4, ReorderKind::F32, 3);
                roundtrip(total, 2, ReorderKind::Bf16, 5);
                roundtrip(total, 1, ReorderKind::None, 9);
            }
        }
    }

    /// Appendix C regression: the exact lengths that SEGFAULT the C core
    /// (final chunk 1/2/3 bytes on the 4-plane path) must split/join cleanly.
    #[test]
    fn appendix_c_crash_lengths_are_clean_here() {
        for total in [
            1usize,
            2,
            3,
            262_144 + 1,
            262_144 + 2,
            262_144 + 3,
            524_288 + 1,
            524_288 + 2,
            524_288 + 3,
        ] {
            roundtrip(total, 4, ReorderKind::F32, 17);
        }
        // dtype16 odd lengths (UB in C source analysis, "OK but overflow"):
        for total in [65usize, 262_145, 1_000_001] {
            roundtrip(total, 2, ReorderKind::Bf16, 19);
        }
    }

    #[test]
    fn plane_sizes_match_the_c_formulas() {
        // C: bufLens[b] = q + (b < remainder); decompress last-chunk:
        // lastDecompLen = lastTotal/n, first (lastTotal%n) planes get +1.
        assert_eq!(
            plane_sizes(262_145, 4),
            vec![65_537, 65_536, 65_536, 65_536]
        );
        assert_eq!(
            plane_sizes(262_146, 4),
            vec![65_537, 65_537, 65_536, 65_536]
        );
        assert_eq!(
            plane_sizes(262_147, 4),
            vec![65_537, 65_537, 65_537, 65_536]
        );
        assert_eq!(plane_sizes(1, 4), vec![1, 0, 0, 0]);
        assert_eq!(plane_sizes(3, 2), vec![2, 1]);
        assert_eq!(plane_sizes(0, 4), vec![0, 0, 0, 0]);
        assert_eq!(plane_sizes(7, 1), vec![7]);
    }

    #[test]
    fn layout_is_the_pure_interleave() {
        // Independent byte-level model (not sharing code with split/join):
        // plane b holds src[j] for every j ≡ b (mod n), in order — applied
        // to REORDERED words for the transform kinds.
        let src: Vec<u8> = (0..137u8).map(|i| i.wrapping_mul(11)).collect();
        for (n, kind) in [
            (4usize, ReorderKind::F32),
            (2, ReorderKind::Bf16),
            (2, ReorderKind::None),
        ] {
            let mut reordered = src.clone();
            crate::reorder::reorder_in_place(kind, &mut reordered);
            let sizes = plane_sizes(src.len(), n);
            let mut expected: Vec<Vec<u8>> = sizes.iter().map(|&s| Vec::with_capacity(s)).collect();
            for (j, &byte) in reordered.iter().enumerate() {
                expected[j % n].push(byte);
            }
            let mut storage: Vec<Vec<u8>> = sizes.iter().map(|&s| vec![0u8; s]).collect();
            {
                let mut planes: Vec<&mut [u8]> =
                    storage.iter_mut().map(|v| v.as_mut_slice()).collect();
                split(&src, &mut planes, kind).expect("split");
            }
            assert_eq!(storage, expected, "n={n} kind={kind:?}");
        }
    }

    #[test]
    fn extract_plane_matches_split_exactly() {
        // the virtual-raw path depends on byte equality with split()
        for total in [
            0usize, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 33, 64, 65, 255, 256, 257, 1000,
        ] {
            let src: Vec<u8> = (0..total).map(|i| ((i * 37 + 11) % 251) as u8).collect();
            for n in [1usize, 2, 4] {
                for kind in [ReorderKind::None, ReorderKind::F32, ReorderKind::Bf16] {
                    if n == 1 && kind != ReorderKind::None {
                        continue; // kind is ignored for n=1 (both paths agree anyway)
                    }
                    let sizes = plane_sizes(total, n);
                    let mut storage: Vec<Vec<u8>> = sizes.iter().map(|&s| vec![0u8; s]).collect();
                    {
                        let mut planes: Vec<&mut [u8]> =
                            storage.iter_mut().map(|v| v.as_mut_slice()).collect();
                        split(&src, &mut planes, kind).expect("split");
                    }
                    for b in 0..n {
                        let mut dst = vec![0u8; sizes[b]];
                        extract_plane(&src, n, b, kind, &mut dst).expect("extract");
                        assert_eq!(dst, storage[b], "total={total} n={n} b={b} kind={kind:?}");
                    }
                }
            }
        }
    }

    #[test]
    fn mismatched_plane_lengths_are_errors() {
        let src = [0u8; 10];
        let mut p0 = [0u8; 3]; // wrong: should be 5/5 per the formula
        let mut p1 = [0u8; 7];
        let err = split(&src, &mut [&mut p0[..], &mut p1[..]], ReorderKind::None).unwrap_err();
        assert!(matches!(err, CodecError::Size(_)));
        let planes: [&[u8]; 2] = [&[0u8; 3], &[0u8; 3]];
        let mut dst = [0u8; 7];
        assert!(join(&planes, &mut dst, ReorderKind::None).is_err());
        let planes3: [&[u8]; 3] = [&[], &[], &[]];
        let mut dst0 = [];
        assert!(join(&planes3, &mut dst0, ReorderKind::None).is_err());
        // F64 belongs to the Phase-4 8-plane path
        let mut pa = [0u8; 5];
        let mut pb = [0u8; 5];
        assert!(split(&src, &mut [&mut pa[..], &mut pb[..]], ReorderKind::F64).is_err());
    }
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        /// split → join is the identity for arbitrary data, lengths and
        /// plane counts (the fused reorder must cancel exactly).
        #[test]
        fn split_join_identity(
            src in proptest::collection::vec(any::<u8>(), 0..2100),
            n in prop_oneof![Just(1usize), Just(2), Just(4)],
            kind_idx in 0..3usize,
        ) {
            let kinds = [ReorderKind::None, ReorderKind::F32, ReorderKind::Bf16];
            let kind = kinds[kind_idx];
            let sizes = plane_sizes(src.len(), n);
            let mut storage: Vec<Vec<u8>> = sizes.iter().map(|&s| vec![0u8; s]).collect();
            {
                let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
                split(&src, &mut planes, kind).unwrap();
            }
            let mut dst = vec![0u8; src.len()];
            {
                let planes: Vec<&[u8]> = storage.iter().map(|v| v.as_slice()).collect();
                join(&planes, &mut dst, kind).unwrap();
            }
            prop_assert_eq!(&dst, &src);
        }
    }
}
