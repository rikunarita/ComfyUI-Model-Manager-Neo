//! N-plane split/join — the ZipNN "byte grouping" pre-transform
//! (Plan §4.5-2, Appendix C.4; N = 1, 2, 4 compatibility + N = 8 and the
//! truncation masks of the Neo extension band, Plan §4.6.2, Phase 4).
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
//!
//! Phase 4 additions (Neo extension band — the C core has NO 8-plane or
//! truncation code paths, so these layouts are Neo-defined; see `dtype.rs`
//! module docs for the mode table and the interoperability rationale):
//!
//! * **8-plane split/join** (`split8`/`join8`): the pure 8-way interleave
//!   (byte k of every u64 word → plane k) with the f64 sign/exponent reorder
//!   fused exactly like the 4-plane f32 path; tail bytes (`total % 8`) go to
//!   planes `0..rem` UNTRANSFORMED, the natural generalisation of the C
//!   in-bounds layout the 2/4-plane paths reproduce byte-exactly.
//! * **Truncated (masked) layouts** (`split_masked`/`join_masked`/
//!   `extract_plane_masked`): whole byte planes dropped by the integer
//!   truncation modes are never materialised; dropped byte positions
//!   reconstruct as ZERO. Masked layouts require word-aligned lengths
//!   (checked) and never carry a bit reorder (truncation exists only for
//!   the Neo integer types, whose `bit_reorder` is 0 — a masked call with
//!   an active kind is refused instead of silently mis-transforming).

use crate::dtype::PlaneMask;
use crate::reorder::{
    ReorderKind, reorder_f64_word, revert_bf16_pair, revert_f32_word, revert_f64_word,
    revert_in_place,
};
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
/// Plane count outside {1,2,4,8}, mismatched plane lengths, or a
/// kind/plane-count mismatch (F64 belongs to the 8-plane path and vice
/// versa).
pub fn split(src: &[u8], planes: &mut [&mut [u8]], kind: ReorderKind) -> CodecResult<()> {
    let total = src.len();
    let n = planes.len();
    validate_layout(n, kind)?;
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
        4 => split4(src, planes, kind),
        _ => split8(src, planes, kind),
    }
    Ok(())
}

/// The (plane count, kind) combinations the layouts define: the F64 reorder
/// is the 8-plane transform; the 8-plane layout accepts None (I64/U64) or
/// F64 (f64/complex128) and nothing else.
fn validate_layout(n: usize, kind: ReorderKind) -> CodecResult<()> {
    if !matches!(n, 1 | 2 | 4 | 8) {
        return Err(CodecError::Unsupported(format!(
            "plane count {n} outside {{1,2,4,8}}"
        )));
    }
    match (n, kind) {
        (8, ReorderKind::F32 | ReorderKind::Bf16) => Err(CodecError::Unsupported(format!(
            "{kind:?} reorder is undefined for 8 planes (F64 or None only)"
        ))),
        (1 | 2 | 4, ReorderKind::F64) => Err(CodecError::Unsupported(
            "F64 reorder belongs to the 8-plane path".to_owned(),
        )),
        _ => Ok(()),
    }
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

/// The u64 word transform (8-plane path): F64 sign/exponent reorder or
/// identity (I64/U64 — `ReorderKind::None`).
#[inline]
fn transform_word64(kind: ReorderKind, u: u64) -> u64 {
    match kind {
        ReorderKind::F64 => reorder_f64_word(u),
        _ => u,
    }
}

/// 8-plane interleave (byte k of every u64 word -> plane k) with the fused
/// f64 sign/exponent reorder; tail bytes (total % 8) go to planes 0..rem
/// UNTRANSFORMED — the natural generalisation of the C in-bounds layout the
/// 2/4-plane paths reproduce byte-exactly (Neo extension band: the C core
/// has no 8-plane code, Plan §4.6.2).
#[allow(clippy::type_complexity)]
fn split8(src: &[u8], planes: &mut [&mut [u8]], kind: ReorderKind) {
    let total = src.len();
    // the nested split_at_mut chain of split4, extended to 8 planes
    let (r7, h7) = planes.split_at_mut(7);
    let (r6, h6) = r7.split_at_mut(6);
    let (r5, h5) = r6.split_at_mut(5);
    let (r4, h4) = r5.split_at_mut(4);
    let (r3, h3) = r4.split_at_mut(3);
    let (r2, h2) = r3.split_at_mut(2);
    let (h0, h1) = r2.split_at_mut(1);
    let (p0, p1, p2, p3, p4, p5, p6, p7) = (
        &mut h0[0][..],
        &mut h1[0][..],
        &mut h2[0][..],
        &mut h3[0][..],
        &mut h4[0][..],
        &mut h5[0][..],
        &mut h6[0][..],
        &mut h7[0][..],
    );

    let words = total / 8;
    let n8 = words / 8; // 64-byte blocks = 8 words -> 8 plane bytes each
    for blk in 0..n8 {
        let s = &src[blk * 64..blk * 64 + 64];
        let mut t = [0u8; 64];
        if kind == ReorderKind::F64 {
            for k in 0..8 {
                let u = u64::from_le_bytes(s[k * 8..k * 8 + 8].try_into().expect("8 bytes"));
                t[k * 8..k * 8 + 8].copy_from_slice(&reorder_f64_word(u).to_le_bytes());
            }
        } else {
            t.copy_from_slice(s);
        }
        let o = blk * 8;
        p0[o..o + 8].copy_from_slice(&[t[0], t[8], t[16], t[24], t[32], t[40], t[48], t[56]]);
        p1[o..o + 8].copy_from_slice(&[t[1], t[9], t[17], t[25], t[33], t[41], t[49], t[57]]);
        p2[o..o + 8].copy_from_slice(&[t[2], t[10], t[18], t[26], t[34], t[42], t[50], t[58]]);
        p3[o..o + 8].copy_from_slice(&[t[3], t[11], t[19], t[27], t[35], t[43], t[51], t[59]]);
        p4[o..o + 8].copy_from_slice(&[t[4], t[12], t[20], t[28], t[36], t[44], t[52], t[60]]);
        p5[o..o + 8].copy_from_slice(&[t[5], t[13], t[21], t[29], t[37], t[45], t[53], t[61]]);
        p6[o..o + 8].copy_from_slice(&[t[6], t[14], t[22], t[30], t[38], t[46], t[54], t[62]]);
        p7[o..o + 8].copy_from_slice(&[t[7], t[15], t[23], t[31], t[39], t[47], t[55], t[63]]);
    }
    // scalar remainder words
    for w in n8 * 8..words {
        let u = u64::from_le_bytes(src[w * 8..w * 8 + 8].try_into().expect("8 bytes"));
        let t = transform_word64(kind, u).to_le_bytes();
        p0[w] = t[0];
        p1[w] = t[1];
        p2[w] = t[2];
        p3[w] = t[3];
        p4[w] = t[4];
        p5[w] = t[5];
        p6[w] = t[6];
        p7[w] = t[7];
    }
    // tail bytes (total % 8): NOT reordered (C tail semantics), plane k gets
    // the k-th tail byte at index `words`
    for k in 0..total % 8 {
        let j = words * 8 + k;
        match k {
            0 => p0[words] = src[j],
            1 => p1[words] = src[j],
            2 => p2[words] = src[j],
            3 => p3[words] = src[j],
            4 => p4[words] = src[j],
            5 => p5[words] = src[j],
            6 => p6[words] = src[j],
            _ => p7[words] = src[j],
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
/// Plane count outside {1,2,4,8}, plane/dst length mismatch, or a
/// kind/plane-count mismatch (F64 belongs to the 8-plane path and vice
/// versa).
pub fn join(planes: &[&[u8]], dst: &mut [u8], kind: ReorderKind) -> CodecResult<()> {
    let n = planes.len();
    validate_layout(n, kind)?;
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
            if join4or8(planes, dst, kind, n, &expect, total) {
                return Ok(()); // word revert already fused into the interleave
            }
        }
    }
    // Generic (non-fused) paths: revert over whole words only — exactly the
    // C `revert_all_floats_*` semantics (chunks_exact ignores the tail).
    revert_in_place(kind, dst);
    Ok(())
}

/// The 4-plane and 8-plane join bodies. Returns `true` when the word revert
/// was FUSED into the interleave (the caller must then skip the generic
/// `revert_in_place` pass — identical bytes, one pass instead of two).
fn join4or8(
    planes: &[&[u8]],
    dst: &mut [u8],
    kind: ReorderKind,
    n: usize,
    expect: &[usize],
    total: usize,
) -> bool {
    if n == 8 {
        return join8(planes, dst, kind, total);
    }
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
        return true;
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
            x0[0], x1[0], x2[0], x3[0], x0[1], x1[1], x2[1], x3[1], x0[2], x1[2], x2[2], x3[2],
            x0[3], x1[3], x2[3], x3[3],
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
    false
}

/// 8-plane interleave back to words with the FUSED f64 revert (exact inverse
/// of `split8`; tail bytes stay un-reverted like the C two-pass semantics).
/// Returns `true` when the revert was fused (kind F64), `false` for the
/// plain interleave (kind None — I64/U64).
fn join8(planes: &[&[u8]], dst: &mut [u8], kind: ReorderKind, total: usize) -> bool {
    let fused = kind == ReorderKind::F64;
    let words = total / 8;
    let n8 = words / 8; // 64-byte blocks = 8 words
    for blk in 0..n8 {
        let o = blk * 64;
        let po = blk * 8;
        let mut t = [0u8; 64];
        for i in 0..8 {
            t[i * 8] = planes[0][po + i];
            t[i * 8 + 1] = planes[1][po + i];
            t[i * 8 + 2] = planes[2][po + i];
            t[i * 8 + 3] = planes[3][po + i];
            t[i * 8 + 4] = planes[4][po + i];
            t[i * 8 + 5] = planes[5][po + i];
            t[i * 8 + 6] = planes[6][po + i];
            t[i * 8 + 7] = planes[7][po + i];
        }
        if fused {
            for k in 0..8 {
                let u = u64::from_le_bytes(t[k * 8..k * 8 + 8].try_into().expect("8 bytes"));
                dst[o + k * 8..o + k * 8 + 8].copy_from_slice(&revert_f64_word(u).to_le_bytes());
            }
        } else {
            dst[o..o + 64].copy_from_slice(&t);
        }
    }
    // scalar remainder words
    for w in n8 * 8..words {
        let mut word = [0u8; 8];
        for (b, p) in planes.iter().enumerate().take(8) {
            word[b] = p[w];
        }
        let u = u64::from_le_bytes(word);
        let t = if fused { revert_f64_word(u) } else { u };
        dst[w * 8..w * 8 + 8].copy_from_slice(&t.to_le_bytes());
    }
    // tail bytes (total % 8): planes b < rem contribute their last byte at
    // index `words` — un-reverted (partial word, C tail semantics)
    for b in 0..total % 8 {
        dst[words * 8 + b] = planes[b][words];
    }
    fused
}

/// Extract a SINGLE plane `b` of the `n`-plane layout of `src` into `dst`
/// (identical bytes to `split(src, planes, kind)`'s `planes[b]`, including
/// the fused word reorder). Used by the codec's "virtual raw plane" path:
/// planes the C heuristics deem incompressible never need a materialised
/// scratch copy — the assembly phase extracts them straight from the source
/// into the output (byte-identical results, one full copy less).
///
/// # Errors
/// Plane index outside the layout, plane count outside {1,2,4,8}, `dst`
/// length mismatch, or a kind/plane-count mismatch (F64 ↔ 8-plane).
pub fn extract_plane(
    src: &[u8],
    n: usize,
    b: usize,
    kind: ReorderKind,
    dst: &mut [u8],
) -> CodecResult<()> {
    if b >= n {
        return Err(CodecError::Unsupported(format!(
            "extract_plane: plane {b} outside the {n}-plane layout"
        )));
    }
    validate_layout(n, kind)?;
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
        8 => {
            // byte k of every (f64-reordered) u64 word → plane k; tail byte
            // k → plane k (untransformed) — the split8 inverse
            let words = total / 8;
            if kind == ReorderKind::None {
                for (i, w) in src[..words * 8].chunks_exact(8).enumerate() {
                    dst[i] = w[b];
                }
            } else {
                for (i, w) in src[..words * 8].chunks_exact(8).enumerate() {
                    let u = u64::from_le_bytes(w.try_into().expect("8 bytes"));
                    dst[i] = transform_word64(kind, u).to_le_bytes()[b];
                }
            }
            if b < total % 8 {
                dst[words] = src[words * 8 + b];
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

// ---------------------------------------------------------------------------
// Truncated (masked) layouts — Neo extension band integer types
// (dtype.rs module docs: whole zero planes are dropped from the payload and
// reconstructed as zeros). Masked layouts are word-aligned by construction
// and never carry a bit reorder (truncation exists only for the Neo integer
// codes, whose `bit_reorder` is 0).
// ---------------------------------------------------------------------------

/// Validate a masked-layout call: n ∈ {2,4} (the truncatable word sizes),
/// kind None, at least one kept plane, and a word-aligned length.
fn validate_masked(
    n: usize,
    kind: ReorderKind,
    mask: &PlaneMask,
    total: usize,
) -> CodecResult<usize> {
    if !matches!(n, 2 | 4) {
        return Err(CodecError::Unsupported(format!(
            "masked (truncated) layouts exist for 2/4 planes only, got {n}"
        )));
    }
    if kind != ReorderKind::None {
        return Err(CodecError::Unsupported(
            "masked (truncated) layouts never carry a bit reorder (Neo integer types only)"
                .to_owned(),
        ));
    }
    if !mask.iter().take(n).any(|k| *k) {
        return Err(CodecError::Unsupported(
            "masked layout keeps no planes at all".to_owned(),
        ));
    }
    if total % n != 0 {
        return Err(CodecError::Size(format!(
            "masked layout requires element-aligned lengths: {total} % {n} != 0"
        )));
    }
    Ok(total / n)
}

/// Masked [`split`]: kept planes receive byte `b` of every word (one byte
/// per element); dropped planes must be zero-length and stay untouched.
///
/// # Errors
/// Invalid masked layout (see [`validate_masked`]) or plane length mismatch.
pub fn split_masked(
    src: &[u8],
    planes: &mut [&mut [u8]],
    kind: ReorderKind,
    mask: &PlaneMask,
) -> CodecResult<()> {
    let n = planes.len();
    let elems = validate_masked(n, kind, mask, src.len())?;
    for (b, p) in planes.iter().enumerate().take(n) {
        let want = if mask[b] { elems } else { 0 };
        if p.len() != want {
            return Err(CodecError::Size(format!(
                "masked plane {b} is {} bytes, layout requires {want}",
                p.len()
            )));
        }
    }
    for b in 0..n {
        if !mask[b] {
            continue;
        }
        let dst = &mut planes[b];
        for (i, w) in src.chunks_exact(n).enumerate() {
            dst[i] = w[b];
        }
    }
    Ok(())
}

/// Masked [`join`]: byte `b` of every output word comes from kept plane `b`
/// (its i-th byte) or is ZERO for dropped planes.
///
/// # Errors
/// Invalid masked layout or plane/dst length mismatch.
pub fn join_masked(
    planes: &[&[u8]],
    dst: &mut [u8],
    kind: ReorderKind,
    mask: &PlaneMask,
) -> CodecResult<()> {
    let n = planes.len();
    let elems = validate_masked(n, kind, mask, dst.len())?;
    for (b, p) in planes.iter().enumerate().take(n) {
        let want = if mask[b] { elems } else { 0 };
        if p.len() != want {
            return Err(CodecError::Size(format!(
                "masked plane {b} is {} bytes, layout for dst {} requires {want}",
                p.len(),
                dst.len()
            )));
        }
    }
    for b in 0..n {
        let src_plane = planes[b];
        if mask[b] {
            for (i, slot) in dst.chunks_exact_mut(n).enumerate() {
                slot[b] = src_plane[i];
            }
        } else {
            for slot in dst.chunks_exact_mut(n) {
                slot[b] = 0;
            }
        }
    }
    Ok(())
}

/// Masked [`extract_plane`]: a dropped plane extracts to an empty `dst`;
/// a kept plane extracts byte `b` of every word.
///
/// # Errors
/// Invalid masked layout or `dst` length mismatch.
pub fn extract_plane_masked(
    src: &[u8],
    n: usize,
    b: usize,
    kind: ReorderKind,
    mask: &PlaneMask,
    dst: &mut [u8],
) -> CodecResult<()> {
    if b >= n {
        return Err(CodecError::Unsupported(format!(
            "extract_plane_masked: plane {b} outside the {n}-plane layout"
        )));
    }
    let elems = validate_masked(n, kind, mask, src.len())?;
    let want = if mask[b] { elems } else { 0 };
    if dst.len() != want {
        return Err(CodecError::Size(format!(
            "extract_plane_masked: dst {} bytes, layout requires {want}",
            dst.len()
        )));
    }
    if !mask[b] {
        return Ok(()); // dropped plane: nothing stored, dst stays empty
    }
    for (i, w) in src.chunks_exact(n).enumerate() {
        dst[i] = w[b];
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
            // Phase 4: the 8-plane path with both of its legal kinds
            for kind in [ReorderKind::None, ReorderKind::F64] {
                roundtrip(total, 8, kind, 31);
            }
        }
    }

    /// The kind/plane-count gate: F64 is 8-plane-only and the u32-based
    /// kinds are undefined for 8 planes (dtype.rs `kind_for` can never
    /// produce those pairs, but the layout functions defend anyway).
    #[test]
    fn invalid_kind_plane_combinations_are_errors() {
        let src = [0u8; 32];
        let mut p8: Vec<Vec<u8>> = vec![vec![0u8; 4]; 8];
        {
            let mut planes: Vec<&mut [u8]> = p8.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split(&src, &mut planes, ReorderKind::F32).is_err());
            assert!(split(&src, &mut planes, ReorderKind::Bf16).is_err());
        }
        let mut p4: Vec<Vec<u8>> = vec![vec![0u8; 8]; 4];
        {
            let mut planes: Vec<&mut [u8]> = p4.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split(&src, &mut planes, ReorderKind::F64).is_err());
        }
        let planes8: Vec<&[u8]> = p8.iter().map(|v| v.as_slice()).collect();
        let mut dst = [0u8; 32];
        assert!(join(&planes8, &mut dst, ReorderKind::F32).is_err());
        // plane count 3 stays rejected
        let mut p3: Vec<Vec<u8>> = vec![vec![0u8; 10]; 3];
        {
            let mut planes: Vec<&mut [u8]> = p3.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split(&src, &mut planes, ReorderKind::None).is_err());
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
                roundtrip(total, 8, ReorderKind::F64, 11);
                roundtrip(total, 8, ReorderKind::None, 13);
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
            for n in [1usize, 2, 4, 8] {
                for kind in [
                    ReorderKind::None,
                    ReorderKind::F32,
                    ReorderKind::Bf16,
                    ReorderKind::F64,
                ] {
                    if n == 1 && kind != ReorderKind::None {
                        continue; // kind is ignored for n=1 (both paths agree anyway)
                    }
                    if (n == 8) != (kind == ReorderKind::F64) && kind != ReorderKind::None {
                        continue; // F64 ↔ 8-plane; F32/Bf16 ↔ 4/2-plane
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

    /// The 8-plane layout is the PURE interleave (byte k of every u64 word
    /// → plane k), with the f64 reorder fused for kind F64 — checked against
    /// a straightforward reference implementation.
    #[test]
    fn layout_8plane_is_the_pure_interleave() {
        let total = 1000; // 125 words, no tail
        let src: Vec<u8> = (0..total).map(|i| ((i * 91 + 17) % 256) as u8).collect();
        for kind in [ReorderKind::None, ReorderKind::F64] {
            let sizes = plane_sizes(total, 8);
            let mut storage: Vec<Vec<u8>> = sizes.iter().map(|&s| vec![0u8; s]).collect();
            {
                let mut planes: Vec<&mut [u8]> =
                    storage.iter_mut().map(|v| v.as_mut_slice()).collect();
                split(&src, &mut planes, kind).expect("split");
            }
            for (b, plane) in storage.iter().enumerate() {
                for w in 0..125 {
                    let word = u64::from_le_bytes(src[w * 8..w * 8 + 8].try_into().unwrap());
                    let t = match kind {
                        ReorderKind::F64 => crate::reorder::reorder_f64_word(word),
                        _ => word,
                    };
                    assert_eq!(
                        plane[w],
                        t.to_le_bytes()[b],
                        "word {w} plane {b} kind {kind:?}"
                    );
                }
            }
        }
        // tail bytes land in planes 0..rem untransformed at index `words`
        let total = 1003; // 125 words + 3 tail bytes
        let src: Vec<u8> = (0..total).map(|i| ((i * 45 + 7) % 256) as u8).collect();
        let sizes = plane_sizes(total, 8);
        assert_eq!(sizes, vec![126, 126, 126, 125, 125, 125, 125, 125]);
        let mut storage: Vec<Vec<u8>> = sizes.iter().map(|&s| vec![0u8; s]).collect();
        {
            let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
            split(&src, &mut planes, ReorderKind::F64).expect("split");
        }
        for k in 0..3 {
            assert_eq!(storage[k][125], src[1000 + k], "tail byte {k}");
        }
    }

    fn masked_roundtrip(total: usize, n: usize, mask: &PlaneMask, seed: u8) {
        // truncation is lossless ONLY when the dropped byte positions are
        // zero (the compressor verifies exactly that) — mirror the contract
        let src: Vec<u8> = (0..total)
            .map(|i| {
                if mask[i % n] {
                    (i as u8).wrapping_mul(seed).wrapping_add(7)
                } else {
                    0
                }
            })
            .collect();
        let elems = total / n;
        let mut storage: Vec<Vec<u8>> = (0..n)
            .map(|b| vec![0u8; if mask[b] { elems } else { 0 }])
            .collect();
        {
            let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
            split_masked(&src, &mut planes, ReorderKind::None, mask).expect("split_masked");
        }
        // extract_plane_masked parity with split_masked (the codec's virtual
        // raw path depends on byte equality)
        for (b, plane) in storage.iter().enumerate().take(n) {
            let mut dst = vec![0u8; plane.len()];
            extract_plane_masked(&src, n, b, ReorderKind::None, mask, &mut dst).expect("extract");
            assert_eq!(&dst, plane, "masked extract parity n={n} b={b}");
        }
        let mut dst = vec![0u8; total];
        {
            let planes: Vec<&[u8]> = storage.iter().map(|v| v.as_slice()).collect();
            join_masked(&planes, &mut dst, ReorderKind::None, mask).expect("join_masked");
        }
        assert_eq!(
            dst, src,
            "masked roundtrip total={total} n={n} mask={mask:?}"
        );
    }

    #[test]
    fn masked_roundtrips_every_truncation_mode() {
        use crate::dtype::plane_mask;
        // 2-plane modes 1 / 8 (I16/U16 truncation)
        for mode in [1u8, 8] {
            let mask = plane_mask(mode, 2).unwrap();
            for total in [0usize, 2, 4, 64, 262_144, 262_146, 1_000_000] {
                masked_roundtrip(total, 2, &mask, 13);
            }
        }
        // 4-plane modes 41 / 9 / 1 (I32/U32 truncation)
        for mode in [41u8, 9, 1] {
            let mask = plane_mask(mode, 4).unwrap();
            for total in [0usize, 4, 8, 64, 262_144, 262_148, 1_000_000] {
                masked_roundtrip(total, 4, &mask, 17);
            }
        }
        // full masks through the masked API behave like split/join
        let full4 = plane_mask(220, 4).unwrap();
        masked_roundtrip(1024, 4, &full4, 19);
        let full2 = plane_mask(10, 2).unwrap();
        masked_roundtrip(1024, 2, &full2, 23);
    }

    #[test]
    fn masked_layouts_reject_misuse() {
        use crate::dtype::plane_mask;
        let mask = plane_mask(41, 4).unwrap();
        // non word-aligned length
        let src = [0u8; 101];
        let mut storage: Vec<Vec<u8>> = vec![vec![0u8; 25]; 3];
        storage.push(Vec::new());
        {
            let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
            let err = split_masked(&src, &mut planes, ReorderKind::None, &mask).unwrap_err();
            assert!(matches!(err, CodecError::Size(_)), "{err:?}");
        }
        // active reorder kind is refused (truncation is integer-only)
        let src = [0u8; 100];
        {
            let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split_masked(&src, &mut planes, ReorderKind::F32, &mask).is_err());
        }
        // wrong plane length
        let mut bad: Vec<Vec<u8>> = vec![vec![0u8; 24]; 3];
        bad.push(Vec::new());
        {
            let mut planes: Vec<&mut [u8]> = bad.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split_masked(&src, &mut planes, ReorderKind::None, &mask).is_err());
        }
        // 8-plane and 1-plane masks do not exist for the masked API
        let mask8 = plane_mask(88, 8).unwrap();
        let src8 = [0u8; 64];
        let mut st8: Vec<Vec<u8>> = vec![vec![0u8; 8]; 8];
        {
            let mut planes: Vec<&mut [u8]> = st8.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split_masked(&src8, &mut planes, ReorderKind::None, &mask8).is_err());
        }
        // an all-dropped mask is refused
        let empty = [false; 8];
        {
            let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
            assert!(split_masked(&src, &mut planes, ReorderKind::None, &empty).is_err());
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

        /// The 8-plane path (Phase 4): split → join is the identity for
        /// arbitrary lengths with both legal kinds.
        #[test]
        fn split_join_identity_8plane(
            src in proptest::collection::vec(any::<u8>(), 0..2100),
            f64 in prop_oneof![Just(true), Just(false)],
        ) {
            let kind = if f64 { ReorderKind::F64 } else { ReorderKind::None };
            let sizes = plane_sizes(src.len(), 8);
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

        /// Masked (truncated) layouts: word-aligned data with all-zero
        /// dropped planes round-trips — dropped positions must come back
        /// as the zeros they were.
        #[test]
        fn masked_split_join_identity(
            base in proptest::collection::vec(any::<u8>(), 0..600),
            n in prop_oneof![Just(2usize), Just(4)],
            mode_idx in 0..3usize,
        ) {
            let modes2 = [1u8, 8, 10];
            let modes4 = [41u8, 9, 1];
            let mode = if n == 2 { modes2[mode_idx] } else { modes4[mode_idx] };
            let mask = crate::dtype::plane_mask(mode, n).unwrap();
            // build a word-aligned source whose dropped-plane bytes are zero
            let elems = base.len() / n;
            let mut src = vec![0u8; elems * n];
            for i in 0..elems {
                for b in 0..n {
                    src[i * n + b] = if mask[b] { base[i * n + b] } else { 0 };
                }
            }
            let mut storage: Vec<Vec<u8>> =
                (0..n).map(|b| vec![0u8; if mask[b] { elems } else { 0 }]).collect();
            {
                let mut planes: Vec<&mut [u8]> = storage.iter_mut().map(|v| v.as_mut_slice()).collect();
                split_masked(&src, &mut planes, ReorderKind::None, &mask).unwrap();
            }
            let mut dst = vec![0u8; src.len()];
            {
                let planes: Vec<&[u8]> = storage.iter().map(|v| v.as_slice()).collect();
                join_masked(&planes, &mut dst, ReorderKind::None, &mask).unwrap();
            }
            prop_assert_eq!(&dst, &src);
        }
    }
}
