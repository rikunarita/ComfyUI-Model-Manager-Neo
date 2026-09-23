//! Huffman tree build — a step-for-step port of `HUF_sort`,
//! `HUF_buildCTable_wksp` and `HUF_setMaxHeight` (vendored
//! `huf_compress.c`). The algorithms are replicated EXACTLY (bucket sort
//! with insertion refinement, the two-queue Huffman merge, the max-height
//! rebalancing, the canonical value assignment) because every one of those
//! choices shifts code lengths and therefore compressed size — byte-exact
//! parity with the C core (Plan §6.2 Phase 1: 圧縮率差 ±0.5% は余裕で満たす
//! ため byte-identical を狙う) and deterministic goldens demand it.

use crate::bitstream::highbit32;
use crate::{CodecError, CodecResult, HUF_TABLELOG_DEFAULT, HUF_TABLELOG_MAX};

/// Encoder-side code table (`HUF_CElt[256]`): canonical code value + length
/// per symbol. Zero-count symbols keep `nb_bits == 0` (the workspace is
/// zeroed on every build — matching the C core's effective behaviour,
/// verified empirically: identical blocks regardless of call history).
#[derive(Debug, Clone)]
pub struct HuffCTable {
    pub val: [u16; 256],
    pub nb_bits: [u8; 256],
    /// Packed hot-path table: `val | (nb_bits << 16)` — one cache-line load
    /// per symbol in the bitstream writer (the C `HUF_CElt` struct plays the
    /// same role).
    pub packed: [u32; 256],
}

/// One node of the Huffman build (`nodeElt`).
#[derive(Debug, Clone, Copy, Default)]
struct NodeElt {
    count: u32,
    parent: u16,
    byte: u8,
    nb_bits: u8,
}

const STARTNODE: usize = 256; // HUF_SYMBOLVALUE_MAX + 1
const RANK_POSITION_TABLE_SIZE: usize = 32;

/// `HUF_sort`: counts → nodes sorted by count DESCENDING; ties keep
/// ascending symbol order (the insertion loop shifts only on strictly
/// greater counts). Bucketed by highbit(count+1) exactly like the C.
fn huf_sort(huff_node: &mut [NodeElt], count: &[u32], max_symbol_value: usize) {
    let mut rank_base = [0u32; RANK_POSITION_TABLE_SIZE];
    for &c in count.iter().take(max_symbol_value + 1) {
        let r = highbit32(c + 1) as usize;
        rank_base[r] += 1;
    }
    // suffix sums: rank_base[r] = start index of bucket r (descending counts)
    for n in (1..=30).rev() {
        rank_base[n - 1] += rank_base[n];
    }
    let mut rank_current = rank_base;
    for (n, &c) in count.iter().enumerate().take(max_symbol_value + 1) {
        let r = (highbit32(c + 1) + 1) as usize;
        let mut pos = rank_current[r] as usize;
        rank_current[r] += 1;
        while pos > rank_base[r] as usize && c > huff_node[pos - 1].count {
            huff_node[pos] = huff_node[pos - 1];
            pos -= 1;
        }
        huff_node[pos].count = c;
        huff_node[pos].byte = n as u8;
    }
}

/// `HUF_setMaxHeight`: rebalance the tree so no code exceeds `max_nb_bits`,
/// paying the cost back from the shortest codes (verbatim port, including
/// the rankLast bookkeeping and the negative-overshoot correction).
fn set_max_height(huff_node: &mut [NodeElt], last_non_null: usize, max_nb_bits: u32) -> u32 {
    let largest_bits = u32::from(huff_node[last_non_null].nb_bits);
    if largest_bits <= max_nb_bits {
        return largest_bits; // early exit: no element too deep
    }
    let mut total_cost: i32 = 0;
    let base_cost: i32 = 1 << (largest_bits - max_nb_bits);
    let mut n = last_non_null as i32;

    while huff_node[n as usize].nb_bits as u32 > max_nb_bits {
        total_cost +=
            base_cost - (1i32 << (largest_bits - u32::from(huff_node[n as usize].nb_bits)));
        huff_node[n as usize].nb_bits = max_nb_bits as u8;
        n -= 1;
    }
    while huff_node[n as usize].nb_bits as u32 == max_nb_bits {
        n -= 1;
    }
    total_cost >>= largest_bits - max_nb_bits;

    const NO_SYMBOL: u32 = 0xF0F0_F0F0;
    let mut rank_last = [NO_SYMBOL; (HUF_TABLELOG_MAX + 2) as usize];
    {
        let mut current_nb_bits = max_nb_bits;
        let mut pos = n;
        while pos >= 0 {
            if u32::from(huff_node[pos as usize].nb_bits) >= current_nb_bits {
                pos -= 1;
                continue;
            }
            current_nb_bits = u32::from(huff_node[pos as usize].nb_bits);
            rank_last[(max_nb_bits - current_nb_bits) as usize] = pos as u32;
            pos -= 1;
        }
    }

    while total_cost > 0 {
        let mut n_bits_to_decrease = highbit32(total_cost as u32) + 1;
        while n_bits_to_decrease > 1 {
            let high_pos = rank_last[n_bits_to_decrease as usize];
            let low_pos = rank_last[(n_bits_to_decrease - 1) as usize];
            if high_pos == NO_SYMBOL {
                n_bits_to_decrease -= 1;
                continue;
            }
            if low_pos == NO_SYMBOL {
                break;
            }
            let high_total = huff_node[high_pos as usize].count;
            let low_total = 2 * huff_node[low_pos as usize].count;
            if high_total <= low_total {
                break;
            }
            n_bits_to_decrease -= 1;
        }
        while n_bits_to_decrease <= HUF_TABLELOG_MAX
            && rank_last[n_bits_to_decrease as usize] == NO_SYMBOL
        {
            n_bits_to_decrease += 1;
        }
        total_cost -= 1 << (n_bits_to_decrease - 1);
        if rank_last[(n_bits_to_decrease - 1) as usize] == NO_SYMBOL {
            rank_last[(n_bits_to_decrease - 1) as usize] = rank_last[n_bits_to_decrease as usize];
        }
        huff_node[rank_last[n_bits_to_decrease as usize] as usize].nb_bits += 1;
        if rank_last[n_bits_to_decrease as usize] == 0 {
            rank_last[n_bits_to_decrease as usize] = NO_SYMBOL;
        } else {
            rank_last[n_bits_to_decrease as usize] -= 1;
            if u32::from(huff_node[rank_last[n_bits_to_decrease as usize] as usize].nb_bits)
                != max_nb_bits - n_bits_to_decrease
            {
                rank_last[n_bits_to_decrease as usize] = NO_SYMBOL;
            }
        }
    }

    while total_cost < 0 {
        if rank_last[1] == NO_SYMBOL {
            while huff_node[n as usize].nb_bits as u32 == max_nb_bits {
                n -= 1;
            }
            huff_node[(n + 1) as usize].nb_bits -= 1;
            rank_last[1] = (n + 1) as u32;
            total_cost += 1;
            continue;
        }
        huff_node[(rank_last[1] + 1) as usize].nb_bits -= 1;
        rank_last[1] += 1;
        total_cost += 1;
    }
    max_nb_bits
}

/// `HUF_buildCTable_wksp`: build the canonical code table from symbol
/// counts. Returns the table and the actual max code length used.
///
/// Node indexing mirrors the C exactly: `huffNode` is `nodes[1..]` so the
/// C's `huffNode[-1]` barrier (count 2^31, set on `nodes[0]`) falls out
/// naturally when `lowS` walks below zero.
///
/// # Errors
/// `max_sv > 255`, or a degenerate distribution (fewer than two non-zero
/// symbols — callers must handle RLE first, like the C does).
pub fn build_c_table(
    count: &[u32; 256],
    max_sv: usize,
    mut max_nb_bits: u32,
) -> CodecResult<(HuffCTable, u32)> {
    if max_sv > 255 {
        return Err(CodecError::Huff0("maxSymbolValue too large".to_owned()));
    }
    if max_nb_bits == 0 {
        max_nb_bits = HUF_TABLELOG_DEFAULT;
    }
    // nodes[0] = the C `huffNode0[0]` barrier; nodes[i+1] == C huffNode[i]
    let mut nodes = vec![NodeElt::default(); STARTNODE + 256 + 2];
    {
        let huff_node = &mut nodes[1..];
        huf_sort(huff_node, count, max_sv);
    }

    // index helpers (C huffNode[i] → nodes[i+1]; i == -1 → the barrier)
    fn cnt(nodes: &[NodeElt], i: i32) -> u32 {
        nodes[(i + 1) as usize].count
    }

    let mut non_null_rank = max_sv as i32;
    while cnt(&nodes, non_null_rank) == 0 {
        non_null_rank -= 1;
    }
    if non_null_rank < 1 {
        return Err(CodecError::Huff0(
            "fewer than two non-zero symbols (RLE must be handled by the caller)".to_owned(),
        ));
    }
    let mut low_s = non_null_rank;
    let node_root = (STARTNODE as i32) + low_s - 1;
    let mut low_n = STARTNODE as i32;
    let mut node_nb = STARTNODE as i32;

    nodes[(node_nb + 1) as usize].count = cnt(&nodes, low_s) + cnt(&nodes, low_s - 1);
    nodes[(low_s + 1) as usize].parent = node_nb as u16;
    nodes[low_s as usize].parent = node_nb as u16; // low_s - 1 + 1
    node_nb += 1;
    low_s -= 2;
    for n in node_nb..=node_root {
        nodes[(n + 1) as usize].count = 1 << 30;
    }
    nodes[0].count = 1 << 31; // fake entry, strong barrier (C huffNode0[0])

    while node_nb <= node_root {
        // n1 = (huffNode[lowS].count < huffNode[lowN].count) ? lowS-- : lowN++
        let n1 = if cnt(&nodes, low_s) < cnt(&nodes, low_n) {
            low_s -= 1;
            low_s + 1
        } else {
            low_n += 1;
            low_n - 1
        };
        // n2: same comparison AFTER the first pick (C re-reads both cursors)
        let n2 = if cnt(&nodes, low_s) < cnt(&nodes, low_n) {
            low_s -= 1;
            low_s + 1
        } else {
            low_n += 1;
            low_n - 1
        };
        nodes[(node_nb + 1) as usize].count = cnt(&nodes, n1) + cnt(&nodes, n2);
        if n1 >= 0 {
            nodes[(n1 + 1) as usize].parent = node_nb as u16;
        }
        if n2 >= 0 {
            nodes[(n2 + 1) as usize].parent = node_nb as u16;
        }
        node_nb += 1;
    }

    // distribute weights (unlimited tree height first)
    nodes[(node_root + 1) as usize].nb_bits = 0;
    let mut n = node_root - 1;
    while n >= STARTNODE as i32 {
        let p = i32::from(nodes[(n + 1) as usize].parent);
        nodes[(n + 1) as usize].nb_bits = nodes[(p + 1) as usize].nb_bits + 1;
        n -= 1;
    }
    for n in 0..=non_null_rank {
        let p = i32::from(nodes[(n + 1) as usize].parent);
        nodes[(n + 1) as usize].nb_bits = nodes[(p + 1) as usize].nb_bits + 1;
    }

    // enforce maxTableLog
    {
        let huff_node = &mut nodes[1..];
        max_nb_bits = set_max_height(huff_node, non_null_rank as usize, max_nb_bits);
    }
    if max_nb_bits > HUF_TABLELOG_MAX {
        return Err(CodecError::Huff0(
            "tree does not fit into tableLog".to_owned(),
        ));
    }

    // fill result: canonical values per rank, symbol order within rank
    let mut tree = HuffCTable {
        val: [0u16; 256],
        nb_bits: [0u8; 256],
        packed: [0u32; 256],
    };
    let alphabet_size = max_sv + 1;
    let mut nb_per_rank = [0u16; (HUF_TABLELOG_MAX + 1) as usize];
    for n in 0..=non_null_rank {
        nb_per_rank[nodes[(n + 1) as usize].nb_bits as usize] += 1;
    }
    let mut val_per_rank = [0u16; (HUF_TABLELOG_MAX + 1) as usize];
    let mut min = 0u16;
    for n in (1..=max_nb_bits as usize).rev() {
        val_per_rank[n] = min;
        min = (min + nb_per_rank[n]) >> 1;
    }
    for n in 0..=non_null_rank {
        let byte = nodes[(n + 1) as usize].byte as usize;
        tree.nb_bits[byte] = nodes[(n + 1) as usize].nb_bits;
    }
    for n in 0..alphabet_size {
        let nb = tree.nb_bits[n] as usize;
        tree.val[n] = val_per_rank[nb];
        val_per_rank[nb] = val_per_rank[nb].wrapping_add(1);
    }
    for n in 0..256 {
        tree.packed[n] = u32::from(tree.val[n]) | (u32::from(tree.nb_bits[n]) << 16);
    }
    Ok((tree, max_nb_bits))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn counts_from(data: &[u8]) -> ([u32; 256], usize) {
        let mut c = [0u32; 256];
        for &b in data {
            c[b as usize] += 1;
        }
        let mut max_sv = 0;
        for (i, &v) in c.iter().enumerate() {
            if v > 0 {
                max_sv = i;
            }
        }
        (c, max_sv)
    }

    /// Kraft equality: Σ 2^-nbBits over non-zero symbols == 1.
    fn assert_kraft(tree: &HuffCTable, max_sv: usize) {
        let mut sum_num = 0u64; // in units of 2^-12
        for s in 0..=max_sv {
            let nb = tree.nb_bits[s];
            if nb > 0 {
                sum_num += 1u64 << (12 - nb);
            }
        }
        assert_eq!(sum_num, 1 << 12, "Kraft sum must be exactly 1");
    }

    /// Canonical property: within each code length, values are consecutive
    /// in symbol order, and shorter codes have numerically smaller prefixes.
    fn assert_canonical(tree: &HuffCTable, max_sv: usize, max_bits: u32) {
        for len in 1..=max_bits {
            let mut prev: Option<u16> = None;
            for s in 0..=max_sv {
                if tree.nb_bits[s] as u32 == len {
                    let v = tree.val[s];
                    assert!(v < 1 << len, "value fits in nbBits");
                    if let Some(p) = prev {
                        assert_eq!(v, p + 1, "consecutive within the rank");
                    }
                    prev = Some(v);
                }
            }
        }
    }

    #[test]
    fn two_symbols() {
        let data = [0u8, 1, 0, 0, 1];
        let (c, msv) = counts_from(&data);
        let (tree, max_bits) = build_c_table(&c, msv, 11).expect("build");
        assert_eq!(max_bits, 1);
        assert_eq!(tree.nb_bits[0], 1);
        assert_eq!(tree.nb_bits[1], 1);
        assert_ne!(tree.val[0], tree.val[1]);
        assert_kraft(&tree, msv);
    }

    #[test]
    fn skewed_respects_max_bits() {
        // extremely skewed: one symbol dominates → deep tree without the cap
        let mut data = vec![0u8; 100_000];
        for i in 1..=40u8 {
            data.push(i);
        }
        let (c, msv) = counts_from(&data);
        let (tree, max_bits) = build_c_table(&c, msv, 11).expect("build");
        assert!(max_bits <= 11, "maxNbBits cap enforced: {max_bits}");
        assert_kraft(&tree, msv);
        assert_canonical(&tree, msv, max_bits);
        // the dominant symbol must have the shortest code
        let shortest = (0..=msv)
            .filter(|&s| c[s] > 0)
            .min_by_key(|&s| tree.nb_bits[s])
            .unwrap();
        assert_eq!(shortest, 0);
    }

    #[test]
    fn flat_256_alphabet() {
        let data: Vec<u8> = (0..2560).map(|i| (i % 256) as u8).collect();
        let (c, msv) = counts_from(&data);
        let (tree, max_bits) = build_c_table(&c, msv, 11).expect("build");
        assert_eq!(max_bits, 8);
        assert!(tree.nb_bits.iter().take(256).all(|&n| n == 8));
        assert_kraft(&tree, msv);
    }

    #[test]
    fn single_symbol_is_an_error_rle_handled_by_caller() {
        let (c, msv) = counts_from(&[7u8; 100]);
        assert!(build_c_table(&c, msv, 11).is_err());
    }

    #[test]
    fn random_distributions_are_valid_trees() {
        // deterministic xorshift over many shapes
        let mut x = 0x2545_F491_4F6C_DD1Du64;
        for case in 0..64u32 {
            let n = 40 + (case as usize) * 997;
            let sigma = 1 + case % 40;
            let mut data = Vec::with_capacity(n);
            for _ in 0..n {
                x ^= x << 13;
                x ^= x >> 7;
                x ^= x << 17;
                // log-normal-ish symbol via multiply-shift
                let v = ((x >> 33) as usize) % (1 << 16);
                let sym = ((v as f64).sqrt() / 256.0 * f64::from(sigma)) as usize;
                data.push((sym.min(255)) as u8);
            }
            let (c, msv) = counts_from(&data);
            let present = (0..=msv).filter(|&s| c[s] > 0).count();
            if present < 2 {
                continue;
            }
            let (tree, max_bits) = build_c_table(&c, msv, 11).expect("build");
            assert!(max_bits <= 11, "case {case}: {max_bits}");
            assert_kraft(&tree, msv);
            assert_canonical(&tree, msv, max_bits);
        }
    }
}
