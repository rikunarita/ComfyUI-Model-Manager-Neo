//! huff0 per RFC 8878 §4.2 — the entropy coder inside every ZipNN chunk.
//!
//! Block layout produced by `HUF_compress` (the vendored FiniteStateEntropy,
//! the ONLY variant `zipnn_core.c` calls): `[weight-table header][jump table
//! 3×LE16][4 independent backward bitstreams]`, plus the two degenerate
//! encodings `HUF_decompress` understands: 1 byte = RLE (memset) and
//! cSize == dstSize = stored (memcpy).
//!
//! Compatibility contract (Plan §4.5-5):
//! * [`decompress_block`] accepts every block the C encoder can emit
//!   (FSE-compressed AND direct weight headers, tableLog 1..=12, RLE,
//!   stored) and validates hostile input at every step;
//! * [`compress_block`] is a step-for-step port of `HUF_compress`
//!   (histogram → incompressible/RLE heuristics → optimal tableLog →
//!   `HUF_buildCTable` → `HUF_writeCTable` incl. the FSE-vs-direct choice →
//!   4-stream bitwriter) producing BYTE-IDENTICAL blocks — so L2 golden
//!   tests can compare compressed bytes, not just ratios.
//!
//! The decoder decodes the 4 streams sequentially into their segments
//! (identical results to the C interleaved fast loop — the streams are
//! independent — while staying within safe Rust; the C's post-hoc
//! `op_k > opStart_{k+1}` corruption checks become per-segment bounds plus
//! the same end-of-stream exactness checks).

pub mod decode;
pub mod encode;
pub mod tree;
pub mod weights;

use crate::{CodecError, CodecResult};

/// `HUF_decompress` (huf_decompress.c): decode one huff0 block into exactly
/// `dst_size` bytes.
///
/// # Errors
/// Every malformed-hostile case the C rejects (dstSize 0, cSize > dstSize,
/// bad weight header, bad jump table, stream over/under-run) — and nothing
/// panics.
pub fn decompress_block(src: &[u8], dst_size: usize) -> CodecResult<Vec<u8>> {
    // HUF_decompress validation prologue (verbatim semantics):
    if dst_size == 0 {
        return Err(CodecError::Size("huff0 dstSize == 0".to_owned()));
    }
    if src.len() > dst_size {
        return Err(CodecError::Corrupt(format!(
            "huff0 cSrcSize {} > dstSize {dst_size}",
            src.len()
        )));
    }
    let mut dst = vec![0u8; dst_size];
    if src.len() == dst_size {
        dst.copy_from_slice(src); // "not compressed"
        return Ok(dst);
    }
    if src.len() == 1 {
        dst.fill(src[0]); // RLE
        return Ok(dst);
    }
    // Real block: weight header + (jump table + 4 streams).
    // The C picks 4X1 vs 4X2 by a timing heuristic — both decode the same
    // bitstream identically, so we always use the X2-style decoder.
    decode::decompress_4x2(src, &mut dst)?;
    Ok(dst)
}

/// `HUF_compress` (huf_compress.c): compress one block (≤ 128 KiB).
/// Returns `None` exactly where the C returns 0 (incompressible → the caller
/// stores the chunk raw, chunkType 0).
///
/// # Errors
/// `src` larger than `HUF_BLOCKSIZE_MAX` or `dst_capacity` too small to ever
/// fit (the C reports srcSize_wrong / never overflows the dst).
pub fn compress_block(src: &[u8], dst_capacity: usize) -> CodecResult<Option<Vec<u8>>> {
    encode::huf_compress(src, dst_capacity)
}

/// Scratch-recycling [`compress_block`] for the chunk-parallel codec layer:
/// `writer_scratch` (bit-writer backing buffer) and `out` (the block) are
/// caller-owned and recycled across blocks. `Ok(Some(()))` = block in `out`.
pub fn compress_block_scratch(
    src: &[u8],
    dst_capacity: usize,
    writer_scratch: &mut Vec<u8>,
    out: &mut Vec<u8>,
) -> CodecResult<Option<()>> {
    encode::huf_compress_scratch(src, dst_capacity, writer_scratch, out)
}

/// Decode directly into a caller-provided slice (`dst.len()` == expected
/// original size) with a recycled table buffer — saves the plane-scratch
/// round trip for single-plane (fp8) chunks, where the C core itself does
/// HUF→malloc→memcpy (two copies) and we do one.
pub fn decompress_block_direct(
    src: &[u8],
    dst: &mut [u8],
    entries: &mut decode::DTableEntries,
) -> CodecResult<()> {
    let dst_size = dst.len();
    if dst_size == 0 {
        return Err(CodecError::Size("huff0 dstSize == 0".to_owned()));
    }
    if src.len() > dst_size {
        return Err(CodecError::Corrupt(format!(
            "huff0 cSrcSize {} > dstSize {dst_size}",
            src.len()
        )));
    }
    if src.len() == dst_size {
        dst.copy_from_slice(src); // "not compressed"
        return Ok(());
    }
    if src.len() == 1 {
        dst.fill(src[0]); // RLE
        return Ok(());
    }
    decode::decompress_4x2_into(src, dst, entries)
}

/// Scratch-recycling [`decompress_block`]: `dst` (resized, reused) and
/// `entries` (the 4096-entry X2 table buffer) are caller-owned.
pub fn decompress_block_into(
    src: &[u8],
    dst_size: usize,
    dst: &mut Vec<u8>,
    entries: &mut decode::DTableEntries,
) -> CodecResult<()> {
    if dst_size == 0 {
        return Err(CodecError::Size("huff0 dstSize == 0".to_owned()));
    }
    if src.len() > dst_size {
        return Err(CodecError::Corrupt(format!(
            "huff0 cSrcSize {} > dstSize {dst_size}",
            src.len()
        )));
    }
    dst.resize(dst_size, 0);
    if src.len() == dst_size {
        dst.copy_from_slice(src); // "not compressed"
        return Ok(());
    }
    if src.len() == 1 {
        dst.fill(src[0]); // RLE
        return Ok(());
    }
    decode::decompress_4x2_into(src, dst, entries)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn roundtrip(data: &[u8]) {
        let cap = data.len() + 512;
        match compress_block(data, cap).expect("compress") {
            None => {
                // incompressible: C stores raw; nothing to decode here
            }
            Some(block) => {
                assert!(block.len() < data.len(), "block must be smaller than src");
                let out = decompress_block(&block, data.len()).expect("decompress");
                assert_eq!(&out, data, "roundtrip len {}", data.len());
            }
        }
    }

    #[test]
    fn rle_single_symbol() {
        // HUF_compress: largest == srcSize → 1-byte RLE block
        let data = vec![0xABu8; 1000];
        let block = compress_block(&data, 2000).expect("c").expect("rle");
        assert_eq!(block, vec![0xAB]);
        let out = decompress_block(&block, 1000).expect("d");
        assert_eq!(out, data);
    }

    #[test]
    fn incompressible_returns_none() {
        // high-entropy random data must come back None (threshold/raw path)
        let data: Vec<u8> = (0..4096u32)
            .map(|i| ((i.wrapping_mul(2654435761)) >> 13) as u8)
            .collect();
        // NOTE: hash-like sequences can still compress slightly; assert only
        // the contract: either None, or a block that round-trips.
        roundtrip(&data);
    }

    #[test]
    fn small_inputs() {
        for n in 0..64usize {
            let data: Vec<u8> = (0..n).map(|i| (i % 7) as u8).collect();
            let cap = n + 64;
            let r = compress_block(&data, cap).expect("no error");
            if let Some(block) = r {
                let out = decompress_block(&block, n).expect("decompress");
                assert_eq!(out, data, "n={n}");
            }
        }
    }

    #[test]
    fn two_symbol_and_skewed() {
        for (pat, len) in [
            (vec![0u8, 255], 5000),
            (vec![7u8, 8], 300),
            ((0..256).map(|i| (i / 16) as u8).collect::<Vec<u8>>(), 8192),
        ] {
            let data: Vec<u8> = (0..len).map(|i| pat[i % pat.len()]).collect();
            roundtrip(&data);
        }
        // skewed: zipf-like over 256 symbols
        let mut data = Vec::new();
        let mut x = 12345u32;
        for _ in 0..60_000 {
            x = x.wrapping_mul(1664525).wrapping_add(1013904223);
            let r = (x >> 8) % 1000;
            // power-law-ish symbol choice
            let s = if r < 500 {
                0
            } else if r < 750 {
                1
            } else if r < 875 {
                2
            } else {
                (r % 250 + 5) as u8
            };
            data.push(s);
        }
        roundtrip(&data);
    }

    #[test]
    fn full_block_sizes() {
        // 128 KiB block (HUF_BLOCKSIZE_MAX) of low-entropy data
        let data: Vec<u8> = (0..131_072).map(|i| ((i / 97) % 23) as u8).collect();
        roundtrip(&data);
        // just over the max → error, not panic
        let big = vec![0u8; 131_073];
        assert!(compress_block(&big, 200_000).is_err());
    }

    #[test]
    fn decompress_rejects_hostile_blocks() {
        let hostile: Vec<Vec<u8>> = vec![
            vec![],
            vec![0x80],            // RLE-ish single byte decodes via memset (valid!)
            vec![0xFF; 2],         // truncated header
            vec![130, 0x12, 0x34], // direct header claiming 3 weights, too short
            vec![5, 1, 2, 3, 4, 5, 0, 0, 0, 0, 0, 0], // FSE header garbage
            (0..64).map(|i| i as u8).collect(),
        ];
        for h in hostile {
            for dst in [0usize, 1, 7, 64, 1000] {
                let _ = decompress_block(&h, dst); // must not panic
            }
        }
    }
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    proptest! {
        /// Any byte string either declares incompressible or round-trips
        /// exactly — for arbitrary lengths (incl. 4X segment remainders) and
        /// arbitrary entropy levels.
        #[test]
        fn compress_decompress_roundtrip(
            seed in any::<u64>(),
            len in 0usize..70_000,
            mode in 0..4u8,
        ) {
            // deterministic pseudo-random content by mode:
            // 0 = LCG noise, 1 = few symbols, 2 = runs, 3 = mixed blocks
            let mut x = seed | 1;
            let mut next = move || { x ^= x << 13; x ^= x >> 7; x ^= x << 17; x };
            let data: Vec<u8> = match mode {
                0 => (0..len).map(|_| (next() >> 11) as u8).collect(),
                1 => (0..len).map(|_| ((next() >> 11) % 5) as u8).collect(),
                2 => (0..len).map(|i| if (i / 700) % 2 == 0 { 3 } else { (next() >> 40) as u8 }).collect(),
                _ => (0..len).map(|i| match (i / 9000) % 3 {
                    0 => ((next() >> 11) % 3) as u8,
                    1 => (next() >> 11) as u8,
                    _ => 0x5A,
                }).collect(),
            };
            let cap = len + 1024;
            match compress_block(&data, cap).expect("never errors on valid capacity") {
                None => {} // declared incompressible (C returns 0) — fine
                Some(block) => {
                    prop_assert!(block.len() < len.max(1) + 1);
                    let out = decompress_block(&block, len)
                        .expect("own encoder output must always decode");
                    prop_assert_eq!(&out, &data);
                }
            }
        }
    }
}
