//! huff0 decoder — ports of `HUF_readDTableX2_wksp` / `HUF_fillDTableX2` /
//! `HUF_fillDTableX2Level2` / `HUF_decodeStreamX2` /
//! `HUF_decompress4X2_usingDTable_internal_body` (vendored
//! `huf_decompress.c`).
//!
//! The C dispatches 4X1 vs 4X2 by a timing heuristic; both interpret the
//! SAME bitstream (the X1/X2 difference is only the internal lookup table),
//! so this decoder always builds the double-symbol (X2) table — output is
//! identical for every valid block, and every corruption case the C rejects
//! is rejected here too (weight-header validation in `weights::read_stats`,
//! jump-table bounds, per-segment exact bit consumption).
//!
//! The four streams are decoded SEQUENTIALLY into their segments instead of
//! the C's interleaved fast loop: the streams are independent, the results
//! are identical, and sequential decoding keeps every write inside its own
//! segment without `unsafe` (the C relies on post-hoc `op_k > opStart_{k+1}`
//! corruption checks for the same guarantee).

use super::weights::WeightTable;
use crate::bitstream::{BitReader, StreamStatus};
use crate::{CodecError, CodecResult};

/// The X2 lookup width: `HUF_TABLELOG_MAX` — the C always builds its X2
/// table at the full 12-bit width (`HUF_CREATE_STATIC_DTABLEX2(DTable,
/// HUF_TABLELOG_MAX)`), independent of the block's own tableLog.
const DT_LOG: u32 = 12;

/// One double-symbol decode entry (`HUF_DEltX2`, 4 bytes in C:
/// U16 sequence + BYTE nbBits + BYTE length).
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DeltX2 {
    /// LE byte pair: low = first symbol, high = second (length 2 entries).
    pub seq: u16,
    /// total bits consumed by the entry (1 or 2 symbols).
    pub nb_bits: u8,
    /// symbols produced: 1 or 2.
    pub length: u8,
}

/// The X2 decode table: a FIXED 4096-entry array — `val & 0xFFF` is then
/// statically in-bounds (no bounds check in the hot lookup).
pub type DTableEntries = [DeltX2; 1usize << DT_LOG_USIZE];
const DT_LOG_USIZE: usize = 12;

/// Allocate a zeroed reusable table buffer (16 KiB).
#[must_use]
pub fn new_dtable_scratch() -> Box<DTableEntries> {
    Box::new(
        [DeltX2 {
            seq: 0,
            nb_bits: 0,
            length: 0,
        }; 1usize << DT_LOG_USIZE],
    )
}

/// The built double-symbol table (borrowed entries view).
struct DTableX2<'a> {
    entries: &'a DTableEntries,
}

/// `HUF_readDTableX2_wksp` + `HUF_fillDTableX2` + `HUF_fillDTableX2Level2`,
/// building into a caller-owned (reusable) entries buffer — the chunk-parallel
/// codec recycles one 16 KiB table per worker thread instead of allocating
/// and zeroing it per block. The fill provably writes ALL 4096 entries
/// (exact-cover property of valid Kraft tables), so no stale data survives.
fn build_dtable_x2_into(wt: &WeightTable, entries: &mut DTableEntries) -> CodecResult<()> {
    let table_log = wt.table_log; // read_stats guarantees 1..=12
    let rank_stats = &wt.rank_stats;

    // maxW: highest weight present ("necessarily finds a solution before 0":
    // the implied last weight is always present)
    let mut max_w = table_log;
    while max_w > 0 && rank_stats[max_w as usize] == 0 {
        max_w -= 1;
    }
    if max_w == 0 {
        return Err(CodecError::Corrupt("huff0 maxWeight == 0".to_owned()));
    }

    // rankStart[w] = start index of weight-w region in the sorted list
    // (regions ASCENDING by weight; symbols ascending within a region)
    let mut rank_start = [0usize; (DT_LOG + 2) as usize];
    let mut next_rank_start = 0usize;
    for w in 1..=max_w as usize {
        rank_start[w] = next_rank_start;
        next_rank_start += rank_stats[w] as usize;
    }
    rank_start[0] = next_rank_start; // weight-0 symbols go to the tail
    let size_of_sort = next_rank_start;

    // sort symbols by weight (counting sort, stable in symbol order)
    let mut sorted = vec![(0u8, 0u8); wt.nb_symbols];
    {
        let mut rs = rank_start;
        for (s, &w) in wt.weights.iter().enumerate().take(wt.nb_symbols) {
            let r = rs[w as usize];
            rs[w as usize] += 1;
            sorted[r] = (s as u8, w);
        }
    }
    rank_start[0] = 0; // "forget 0w symbols; this is beginning of weight(1)"

    // rankVal: row 0 = level-1 starts; row `consumed` = row0 >> consumed
    let rescale = DT_LOG as i32 - table_log as i32 - 1; // ∈ [-1, 10]
    let mut rank_val0 = [0u32; (DT_LOG + 1) as usize];
    let mut next_rank_val = 0u32;
    for w in 1..=max_w as usize {
        rank_val0[w] = next_rank_val;
        let shift = (w as i32 + rescale) as u32; // w ≥ 1, rescale ≥ -1 → ≥ 0
        next_rank_val += rank_stats[w] << shift;
    }
    let min_bits = table_log + 1 - max_w;
    let mut rank_val = [[0u32; (DT_LOG + 1) as usize]; DT_LOG as usize];
    rank_val[0] = rank_val0;
    let mut consumed = min_bits;
    while consumed < DT_LOG - min_bits + 1 {
        for w in 1..=max_w as usize {
            rank_val[consumed as usize][w] = rank_val0[w] >> consumed;
        }
        consumed += 1;
    }

    // fillDTableX2
    let baseline = table_log + 1;
    let scale_log = baseline as i32 - DT_LOG as i32; // ≤ 1
    // The fill below provably writes ALL 4096 entries (exact-cover property
    // of valid Kraft tables), so no pre-zeroing of the reused scratch is
    // needed.
    let mut rank_val_l1 = rank_val0; // level-1 works on row 0 (C memcpy)
    for si in 0..size_of_sort {
        let (symbol, w) = sorted[si];
        let nb_bits = baseline - u32::from(w);
        let start = rank_val_l1[w as usize] as usize;
        let length = 1usize << (DT_LOG - nb_bits);
        if DT_LOG - nb_bits >= min_bits {
            // enough room for a second symbol → double-symbol sub-table
            let min_weight = (nb_bits as i32 + scale_log).max(1) as usize;
            let sorted_rank = rank_start[min_weight];
            fill_level2(
                &mut entries[start..start + length],
                DT_LOG - nb_bits,
                nb_bits,
                &rank_val[nb_bits as usize],
                min_weight,
                &sorted[sorted_rank..size_of_sort],
                baseline,
                symbol,
            );
        } else {
            let e = DeltX2 {
                seq: u16::from(symbol),
                nb_bits: nb_bits as u8,
                length: 1,
            };
            entries[start..start + length].fill(e);
        }
        rank_val_l1[w as usize] += length as u32;
    }
    Ok(())
}

/// `HUF_fillDTableX2Level2`.
#[allow(clippy::too_many_arguments)] // faithful port of the C signature
fn fill_level2(
    entries: &mut [DeltX2],
    size_log: u32,
    consumed: u32,
    rank_val_row: &[u32; (DT_LOG + 1) as usize],
    min_weight: usize,
    sorted_suffix: &[(u8, u8)],
    baseline: u32,
    base_seq: u8,
) {
    let mut rank_val = *rank_val_row;
    if min_weight > 1 {
        // values whose next bits start a code lighter than min_weight decode
        // only the first symbol (the pair does not fit in the window)
        let skip_size = rank_val[min_weight] as usize;
        let e = DeltX2 {
            seq: u16::from(base_seq),
            nb_bits: consumed as u8,
            length: 1,
        };
        for slot in entries.iter_mut().take(skip_size) {
            *slot = e;
        }
    }
    for &(symbol2, w2) in sorted_suffix {
        let nb_bits2 = baseline - u32::from(w2);
        let length2 = 1usize << (size_log - nb_bits2); // ≥ 0 shift: w2 ≥ minWeight
        let start2 = rank_val[w2 as usize] as usize;
        let e = DeltX2 {
            seq: u16::from(base_seq) | (u16::from(symbol2) << 8),
            nb_bits: (nb_bits2 + consumed) as u8,
            length: 2,
        };
        entries[start2..start2 + length2].fill(e);
        rank_val[w2 as usize] += length2 as u32;
    }
}

/// `HUF_decodeLastSymbolX2` — the final odd symbol, with the C's
/// bits-consumed clamp ("ugly hack; works only because it's the last
/// symbol").
#[inline]
fn decode_last_symbol(dt: &DTableX2, bitd: &mut BitReader<'_>, seg: &mut [u8], p: usize) -> usize {
    let val = (bitd.look_bits_fast(DT_LOG) & 0xFFF) as usize;
    let e = dt.entries[val];
    seg[p] = e.seq.to_le_bytes()[0];
    if e.length == 1 {
        bitd.skip_bits(u32::from(e.nb_bits));
    } else if bitd.consumed() < 64 {
        bitd.skip_bits(u32::from(e.nb_bits));
        if bitd.consumed() > 64 {
            bitd.set_consumed(64);
        }
    }
    1
}

/// Per-stream "finish" phase (`HUF_decodeStreamX2` minus its fast loop):
/// decode from cursor `p` to exactly `seg.len()`, then require the
/// bitstream to be consumed exactly (C's `BIT_endOfDStream` endCheck).
fn finish_stream(
    dt: &DTableX2,
    bitd: &mut BitReader<'_>,
    seg: &mut [u8],
    p: &mut usize,
) -> CodecResult<()> {
    let entries = &dt.entries;
    let p_end = seg.len();
    // close to the end: up to 2 symbols per (safe) reload
    while *p + 2 <= p_end && bitd.reload() == StreamStatus::Unfinished {
        let w: &mut [u8; 2] = (&mut seg[*p..*p + 2]).try_into().expect("2-byte window");
        *p += decode_symbol_w2x2(entries, bitd, w);
    }
    // no more reloads: drain the register (C: "reached the end of DStream")
    while *p + 2 <= p_end {
        let w: &mut [u8; 2] = (&mut seg[*p..*p + 2]).try_into().expect("2-byte window");
        *p += decode_symbol_w2x2(entries, bitd, w);
    }
    if *p < p_end {
        *p += decode_last_symbol(dt, bitd, seg, *p);
    }
    if *p != p_end {
        return Err(CodecError::Corrupt(
            "huff0 stream overran its segment".to_owned(),
        ));
    }
    if !bitd.end_of_stream() {
        return Err(CodecError::Corrupt(
            "huff0 bitstream not consumed exactly (corruption_detected)".to_owned(),
        ));
    }
    Ok(())
}

/// Window decoders taking the entry slice directly (saves a deref hop in
/// the hot loop). NOTE on the 2-byte window: an entry with length 2 needs
/// w.len()==2 ✓; length 1 writes both bytes (the second is garbage that
/// the next window overwrites, exactly like the C's unconditional memcpy —
/// the window's second byte is always in-segment because p+2 ≤ p_end).
#[inline]
fn decode_symbol_w2x(
    dt: &DTableEntries,
    bitd: &mut BitReader<'_>,
    w: &mut [u8; 8],
    q: usize,
) -> usize {
    // the explicit mask lets LLVM prove val < 4096 == dt.len() and elide
    // the bounds check (look_bits_fast already returns ≤ 12 bits)
    let val = (bitd.look_bits_fast(DT_LOG) & 0xFFF) as usize;
    let e = dt[val];
    w[q..q + 2].copy_from_slice(&e.seq.to_le_bytes());
    bitd.skip_bits(u32::from(e.nb_bits));
    e.length as usize
}

#[inline]
fn decode_symbol_w2x2(dt: &DTableEntries, bitd: &mut BitReader<'_>, w: &mut [u8; 2]) -> usize {
    let val = (bitd.look_bits_fast(DT_LOG) & 0xFFF) as usize;
    let e = dt[val];
    w.copy_from_slice(&e.seq.to_le_bytes());
    bitd.skip_bits(u32::from(e.nb_bits));
    e.length as usize
}

/// `HUF_decompress4X2_usingDTable_internal_body` (+ the readDTable prologue
/// of `HUF_decompress4X2_DCtx_wksp`): decode a full huff0 block (weight
/// header + jump table + 4 streams) into `dst`.
///
/// # Errors
/// Bad weight header (`read_stats`), no bitstream after the header
/// (`hSize >= cSrcSize`), body < 10 bytes, jump-table overflow — every
/// corruption path the C rejects.
pub fn decompress_4x2(src: &[u8], dst: &mut [u8]) -> CodecResult<()> {
    let mut entries = new_dtable_scratch();
    decompress_4x2_into(src, dst, &mut entries)
}

/// Scratch-recycling variant: `entries` is the reusable 4096-entry table
/// buffer (see [`build_dtable_x2_into`]).
pub fn decompress_4x2_into(
    src: &[u8],
    dst: &mut [u8],
    entries: &mut DTableEntries,
) -> CodecResult<()> {
    let wt = super::weights::read_stats(src)?;
    if wt.header_size >= src.len() {
        return Err(CodecError::Corrupt(
            "huff0 header consumes the whole block".to_owned(),
        ));
    }
    let body = &src[wt.header_size..];
    if body.len() < 10 {
        // C: strict minimum = jump table + 1 byte per stream
        return Err(CodecError::Corrupt(format!(
            "huff0 body {} < 10 bytes",
            body.len()
        )));
    }
    build_dtable_x2_into(&wt, entries)?;
    let dt = DTableX2 { entries };

    let l1 = u16::from_le_bytes([body[0], body[1]]) as usize;
    let l2 = u16::from_le_bytes([body[2], body[3]]) as usize;
    let l3 = u16::from_le_bytes([body[4], body[5]]) as usize;
    let sum = 6 + l1 + l2 + l3;
    if sum > body.len() {
        // C computes length4 = cSrcSize - sum in size_t and catches the wrap
        return Err(CodecError::Corrupt(
            "huff0 jump table exceeds block".to_owned(),
        ));
    }
    let l4 = body.len() - sum;
    let (s1, s2) = (6, 6 + l1);
    let (s3, s4) = (6 + l1 + l2, 6 + l1 + l2 + l3);

    let dst_size = dst.len();
    // The C only reaches the 4X path with cSrcSize < dstSize and body ≥ 10,
    // hence dstSize ≥ 11 and the segment math below never overruns; guard
    // anyway (hostile callers of the public API).
    let segment = dst_size.div_ceil(4);
    let e1 = segment.min(dst_size);
    let e2 = (2 * segment).min(dst_size);
    let e3 = (3 * segment).min(dst_size);

    // Disjoint segment slices (safe aliasing) + four independent readers.
    let (seg1, rest) = dst.split_at_mut(e1);
    let (seg2, rest) = rest.split_at_mut(e2 - e1);
    let (seg3, seg4) = rest.split_at_mut(e3 - e2);
    let mut bd1 = BitReader::init(&body[s1..s1 + l1])?;
    let mut bd2 = BitReader::init(&body[s2..s2 + l2])?;
    let mut bd3 = BitReader::init(&body[s3..s3 + l3])?;
    let mut bd4 = BitReader::init(&body[s4..s4 + l4])?;
    let (mut p1, mut p2, mut p3, mut p4) = (0usize, 0usize, 0usize, 0usize);

    // INTERLEAVED fast phase — the C's ILP structure (four independent
    // decode chains in flight, `BIT_reloadDStreamFast` + endSignal), with
    // 8-byte stack windows keeping every store provably in-segment:
    // all four chains must have ≥8 bytes of headroom and reload cleanly;
    // each chain then consumes one window of 4 entries (≤48 bits ≤ the 57
    // available after an unfinished reload — same arithmetic the C relies
    // on between its reloads).
    let ents = dt.entries;
    while p1 + 8 <= seg1.len()
        && p2 + 8 <= seg2.len()
        && p3 + 8 <= seg3.len()
        && p4 + 8 <= seg4.len()
        && bd1.reload_fast() == StreamStatus::Unfinished
        && bd2.reload_fast() == StreamStatus::Unfinished
        && bd3.reload_fast() == StreamStatus::Unfinished
        && bd4.reload_fast() == StreamStatus::Unfinished
    {
        let w1: &mut [u8; 8] = (&mut seg1[p1..p1 + 8]).try_into().expect("w1");
        let mut q = 0usize;
        q += decode_symbol_w2x(ents, &mut bd1, w1, q);
        q += decode_symbol_w2x(ents, &mut bd1, w1, q);
        q += decode_symbol_w2x(ents, &mut bd1, w1, q);
        q += decode_symbol_w2x(ents, &mut bd1, w1, q);
        p1 += q;
        let w2: &mut [u8; 8] = (&mut seg2[p2..p2 + 8]).try_into().expect("w2");
        let mut q = 0usize;
        q += decode_symbol_w2x(ents, &mut bd2, w2, q);
        q += decode_symbol_w2x(ents, &mut bd2, w2, q);
        q += decode_symbol_w2x(ents, &mut bd2, w2, q);
        q += decode_symbol_w2x(ents, &mut bd2, w2, q);
        p2 += q;
        let w3: &mut [u8; 8] = (&mut seg3[p3..p3 + 8]).try_into().expect("w3");
        let mut q = 0usize;
        q += decode_symbol_w2x(ents, &mut bd3, w3, q);
        q += decode_symbol_w2x(ents, &mut bd3, w3, q);
        q += decode_symbol_w2x(ents, &mut bd3, w3, q);
        q += decode_symbol_w2x(ents, &mut bd3, w3, q);
        p3 += q;
        let w4: &mut [u8; 8] = (&mut seg4[p4..p4 + 8]).try_into().expect("w4");
        let mut q = 0usize;
        q += decode_symbol_w2x(ents, &mut bd4, w4, q);
        q += decode_symbol_w2x(ents, &mut bd4, w4, q);
        q += decode_symbol_w2x(ents, &mut bd4, w4, q);
        q += decode_symbol_w2x(ents, &mut bd4, w4, q);
        p4 += q;
    }

    // finish each stream exactly (tail loops + exact-consumption checks)
    finish_stream(&dt, &mut bd1, seg1, &mut p1)?;
    finish_stream(&dt, &mut bd2, seg2, &mut p2)?;
    finish_stream(&dt, &mut bd3, seg3, &mut p3)?;
    finish_stream(&dt, &mut bd4, seg4, &mut p4)?;
    Ok(())
}
