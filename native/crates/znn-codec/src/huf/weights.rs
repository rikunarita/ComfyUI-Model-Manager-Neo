//! huff0 weight-table (code-length) headers — `HUF_readStats` (decoder) and
//! `HUF_writeCTable` + `HUF_compressWeights` (encoder), ported from the
//! vendored `entropy_common.c` / `huf_compress.c` (2026-09-23).
//!
//! Two serializations (RFC 8878 §4.2.1):
//! * header byte ≥ 128: DIRECT — `128 + (nWeights-1)`, then the weights as
//!   4-bit nibble pairs (high nibble first);
//! * header byte < 128: the weight list FSE-compressed into that many bytes.
//!
//! The LAST symbol's weight is implicit in both: it completes the Kraft sum
//! to a power of two (`lastWeight = highbit(2^tableLog - weightTotal) + 1`,
//! validated to be a clean power of two).

use crate::bitstream::highbit32;
use crate::fse;
use crate::{CodecError, CodecResult};
use crate::{HUF_TABLELOG_DEFAULT, HUF_TABLELOG_MAX};

/// Parsed weight header (`HUF_readStats` output).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WeightTable {
    /// weights\[0..nb_symbols\] — including the implied last weight.
    pub weights: Vec<u8>,
    /// number of symbols = explicit weights + 1.
    pub nb_symbols: usize,
    /// the tree's tableLog (Kraft sum = 2^tableLog).
    pub table_log: u32,
    /// count of symbols per weight (indices 0..=12).
    pub rank_stats: [u32; (HUF_TABLELOG_MAX + 1) as usize],
    /// bytes consumed by the header.
    pub header_size: usize,
}

/// `HUF_readStats`: parse the weight header at the front of a huff0 block.
///
/// # Errors
/// Every corruption case the C rejects: srcSize 0, truncated direct/FSE
/// header, weight ≥ 12, weightTotal 0, non-power-of-two remainder,
/// tableLog > 12, rankStats\[1\] < 2 or odd.
pub fn read_stats(src: &[u8]) -> CodecResult<WeightTable> {
    if src.is_empty() {
        return Err(CodecError::Huff0("empty weight header".to_owned()));
    }
    let i_size0 = src[0];
    let mut weights = vec![0u8; 256]; // HUF_SYMBOLVALUE_MAX + 1
    // o_size = number of EXPLICIT weights; header_size = bytes consumed
    let (o_size, header_size) = if i_size0 >= 128 {
        // direct nibble path (o_size = i_size0 - 127 ≤ 128 < 256 always)
        let o = (i_size0 - 127) as usize;
        let nibble_bytes = o.div_ceil(2);
        if nibble_bytes + 1 > src.len() {
            return Err(CodecError::Huff0(
                "truncated direct weight header".to_owned(),
            ));
        }
        debug_assert!(o < 256);
        for n in (0..o).step_by(2) {
            let byte = src[1 + n / 2];
            weights[n] = byte >> 4;
            weights[n + 1] = byte & 15; // writes weights[o_size] when odd —
            // overwritten by the implied weight below (C quirk, mirrored)
        }
        (o, nibble_bytes + 1)
    } else {
        // FSE-compressed weights
        let i_size = i_size0 as usize;
        if i_size + 1 > src.len() {
            return Err(CodecError::Huff0("truncated FSE weight header".to_owned()));
        }
        // C: FSE_decompress_wksp(huffWeight, hwSize-1 = 255, ip+1, iSize, ..., maxLog 6)
        let decoded = fse::decompress(&src[1..1 + i_size], 255, fse::WEIGHT_HEADER_MAX_LOG)?;
        let o = decoded.len();
        weights[..o].copy_from_slice(&decoded);
        (o, i_size + 1)
    };

    // collect weight stats
    let mut rank_stats = [0u32; (HUF_TABLELOG_MAX + 1) as usize];
    let mut weight_total: u32 = 0;
    for w in &weights[..o_size] {
        if u32::from(*w) >= HUF_TABLELOG_MAX {
            return Err(CodecError::Corrupt(format!(
                "huff0 weight {w} >= TABLELOG_MAX"
            )));
        }
        rank_stats[*w as usize] += 1;
        weight_total += (1u32 << *w) >> 1;
    }
    if weight_total == 0 {
        return Err(CodecError::Corrupt("huff0 weightTotal == 0".to_owned()));
    }
    // implied last weight
    let table_log = highbit32(weight_total) + 1;
    if table_log > HUF_TABLELOG_MAX {
        return Err(CodecError::Corrupt(format!(
            "huff0 tableLog {table_log} > {HUF_TABLELOG_MAX}"
        )));
    }
    let total = 1u32 << table_log;
    let rest = total - weight_total;
    let verif = 1u32 << highbit32(rest);
    if verif != rest {
        return Err(CodecError::Corrupt(
            "huff0 implied last weight is not a clean power of two".to_owned(),
        ));
    }
    let last_weight = (highbit32(rest) + 1) as u8;
    weights[o_size] = last_weight;
    rank_stats[last_weight as usize] += 1;
    // tree validity: at least two weight-1 symbols, and an even count of them
    if rank_stats[1] < 2 || rank_stats[1] % 2 == 1 {
        return Err(CodecError::Corrupt(format!(
            "huff0 rankStats[1] = {} invalid (must be even and >= 2)",
            rank_stats[1]
        )));
    }
    let nb_symbols = o_size + 1;
    weights.truncate(nb_symbols);
    Ok(WeightTable {
        weights,
        nb_symbols,
        table_log,
        rank_stats,
        header_size,
    })
}

/// `HUF_compressWeights`: FSE-compress the weight list. Mirrors the C return
/// protocol: `None` = not compressible (C 0), `Some(vec![x])` single byte =
/// RLE marker (C 1 — makes the caller's `hSize > 1` test fail → direct path),
/// `Some(bytes)` = the FSE header+stream.
pub fn compress_weights(weight_table: &[u8]) -> CodecResult<Option<Vec<u8>>> {
    let wt_size = weight_table.len();
    if wt_size <= 1 {
        return Ok(None); // not compressible
    }
    // histogram over weights (alphabet 0..=12)
    let mut count = [0u32; (HUF_TABLELOG_MAX + 1) as usize];
    let mut max_sv: u32 = 0;
    for &w in weight_table {
        count[w as usize] += 1;
        if u32::from(w) > max_sv {
            max_sv = u32::from(w);
        }
    }
    let max_count = *count.iter().max().unwrap_or(&0);
    if max_count as usize == wt_size {
        return Ok(Some(vec![0])); // C returns 1 (RLE marker); content unused,
        // only `hSize > 1` matters → any 1-byte vec
    }
    if max_count == 1 {
        return Ok(None); // every symbol at most once → not compressible
    }
    let table_log = fse::optimal_table_log(fse::WEIGHT_HEADER_MAX_LOG, wt_size, max_sv, 2);
    let Some((norm, log)) =
        fse::normalize_count(&count[..=max_sv as usize], wt_size, max_sv, table_log)?
    else {
        return Ok(None); // RLE case → caller falls back to direct (C: CHECK_F(0) then writes garbage-free? no: normalize returns 0 → C continues with norm=...; unreachable because maxCount==wtSize handled above)
    };
    let mut out = Vec::with_capacity(wt_size + 16);
    fse::write_n_count(&mut out, &norm, max_sv, log)?;
    let ct = fse::build_c_table(&norm, max_sv, log)?;
    // FSE_compress_usingCTable into the tail (fast mode: dst is huge in C's
    // writeCTable context; use the same bound rule for identical bytes)
    let payload_cap = wt_size + (wt_size >> 7) + 4 + 8 + 64;
    let Some(payload) = fse::compress_using_ctable(&ct, weight_table, payload_cap)? else {
        return Ok(None); // cSize == 0 → not enough space → direct path
    };
    out.extend_from_slice(&payload);
    Ok(Some(out))
}

/// `HUF_writeCTable`: serialize the code-length table of a built Huffman
/// tree. `nb_bits[0..=max_sv]` are the code lengths (0 = absent symbol);
/// the LAST symbol's weight is implicit. Appends the header to `out` and
/// returns its size. Chooses FSE-vs-direct exactly like the C:
/// FSE when `1 < hSize < max_sv / 2`.
///
/// # Errors
/// `max_sv` beyond 255 (C: maxSymbolValue_tooLarge / GENERIC).
pub fn write_c_table(
    out: &mut Vec<u8>,
    nb_bits: &[u8],
    max_sv: usize,
    huff_log: u32,
) -> CodecResult<usize> {
    if max_sv > 255 {
        return Err(CodecError::Huff0("maxSymbolValue too large".to_owned()));
    }
    // convert code lengths → weights (bitsToWeight[nb] = huffLog + 1 - nb;
    // absent symbols have nb_bits 0 → weight 0 via bitsToWeight[0] = 0)
    let mut huff_weight = vec![0u8; max_sv + 1];
    for (n, item) in huff_weight.iter_mut().enumerate().take(max_sv) {
        let nb = nb_bits[n];
        *item = if nb == 0 {
            0
        } else {
            debug_assert!(u32::from(nb) <= huff_log);
            (huff_log + 1 - u32::from(nb)) as u8
        };
    }
    huff_weight[max_sv] = 0; // C sentinel (kept out of the FSE input)

    // attempt FSE compression of the weights
    if let Some(fse_bytes) = compress_weights(&huff_weight[..max_sv])? {
        let h_size = fse_bytes.len();
        if h_size > 1 && h_size < max_sv / 2 {
            out.push(h_size as u8);
            out.extend_from_slice(&fse_bytes);
            return Ok(h_size + 1);
        }
    }
    // direct nibble path
    if max_sv == 0 || max_sv > 256 - 128 {
        // C: maxSymbolValue==0 cannot reach here (RLE handled upstream);
        // >128 errors with GENERIC ("should not happen").
        return Err(CodecError::Huff0(
            "maxSymbolValue out of range for the direct weight header".to_owned(),
        ));
    }
    out.push(u8::try_from(128 + (max_sv - 1)).expect("max_sv ≤ 128 checked above"));
    for n in (0..max_sv).step_by(2) {
        out.push((huff_weight[n] << 4) + huff_weight[n + 1]); // [n+1] = sentinel 0 when odd
    }
    Ok(max_sv.div_ceil(2) + 1)
}

/// `HUF_optimalTableLog`: the tableLog the C encoder picks for a block
/// (`FSE_optimalTableLog_internal(11, srcSize, maxSV, minus=1)`).
#[must_use]
pub fn optimal_table_log(src_size: usize, max_symbol_value: u32) -> u32 {
    fse::optimal_table_log(HUF_TABLELOG_DEFAULT, src_size, max_symbol_value, 1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn direct_header_roundtrip() {
        // weights for a tiny tree: nb_bits [1,2,3,3] → huffLog=3 →
        // weights = [3,2,1,(1 implied)] → explicit [3,2,1]
        let nb_bits = [1u8, 2, 3, 3, 0, 0];
        let mut out = Vec::new();
        let size = write_c_table(&mut out, &nb_bits, 3, 3).expect("write");
        assert_eq!(size, out.len());
        assert!(out[0] >= 128, "tiny tables take the direct path");
        let wt = read_stats(&out).expect("read");
        assert_eq!(wt.weights, vec![3, 2, 1, 1]);
        assert_eq!(wt.nb_symbols, 4);
        assert_eq!(wt.table_log, 3);
        assert_eq!(wt.header_size, size);
    }

    #[test]
    fn read_stats_rejects_hostile() {
        let hostile: Vec<&[u8]> = vec![
            &[],
            &[0],               // FSE len 0
            &[200],             // direct nW=73, no bytes
            &[200, 0x11],       // direct nW=73, truncated
            &[128, 0x00],       // nWeights=1 → weightTotal from [0]+implied → rankStats[1]<2
            &[129, 0xFF, 0xFF], // weights 15,15 ≥ 12 → corrupt
            &[130, 0x11, 0x11], // weights [1,1,1]: total=3 → rest=1 → last=1 → rankStats[1]=4 ok? total 3 → tableLog=2, rest=1 ✓ last=1 → rank1 = 3+1=4 even ✓ VALID — must parse
        ];
        for (i, h) in hostile.iter().enumerate() {
            let r = read_stats(h); // must not panic regardless
            if i == 6 {
                assert!(r.is_ok(), "case {i} should actually be valid: {r:?}");
            }
        }
        // explicit invalid ones
        assert!(read_stats(&[]).is_err());
        assert!(read_stats(&[200]).is_err());
        assert!(read_stats(&[129, 0xFF, 0xFF]).is_err());
    }

    #[test]
    fn kraft_valid_profile_roundtrips() {
        // A complete two-level code: 4 symbols of length 3 + 4 of length 3
        // would violate Kraft — use a real complete profile instead:
        // lengths [1?] impossible with rank1-even rule; use [2,2,2,2,3,3,3,3]?
        // Kraft: 4*2^-2 + 4*2^-3 = 1 + 0.5 > 1 — invalid. The canonical
        // complete profile: 2 symbols @2 bits (1/2) + 4 @3 bits (1/2) = 1 ✓
        let nb_bits = [2u8, 2, 3, 3, 3, 3];
        let huff_log = 3;
        let mut out = Vec::new();
        let size = write_c_table(&mut out, &nb_bits, 5, huff_log).expect("write");
        assert_eq!(out.len(), size);
        let wt = read_stats(&out).expect("read");
        assert_eq!(wt.weights, vec![2, 2, 1, 1, 1, 1], "weights = huffLog+1-nb");
        assert_eq!(wt.nb_symbols, 6);
        assert_eq!(wt.table_log, 3);
    }

    #[test]
    fn two_symbol_minimum_tree() {
        // both symbols 1 bit: nb_bits [1,1] — weights [1, implied 1]
        let nb_bits = [1u8, 1];
        let mut out = Vec::new();
        let size = write_c_table(&mut out, &nb_bits, 1, 1).expect("write");
        assert_eq!(out, vec![128, 0x10]);
        assert_eq!(size, 2);
        let wt = read_stats(&out).expect("read");
        assert_eq!(wt.weights, vec![1, 1]);
        assert_eq!(wt.table_log, 1);
    }

    #[test]
    fn flat_full_alphabet_hits_the_c_direct_path_error() {
        // 256 symbols, all code length 8 → all weights 1 → compress_weights
        // sees a single distinct symbol → RLE marker (len 1) → `hSize > 1`
        // fails → the C falls into the DIRECT path, which REJECTS
        // maxSymbolValue > 128 (ERROR(GENERIC) "should not happen"). zipnn
        // then stores the chunk raw. Mirror: write_c_table errors.
        let nb_bits = [8u8; 256];
        let mut out = Vec::new();
        assert!(write_c_table(&mut out, &nb_bits, 255, 8).is_err());
        // 129 symbols is still over the 128 limit:
        let nb_bits = [7u8; 130];
        let mut out = Vec::new();
        assert!(write_c_table(&mut out, &nb_bits, 129, 7).is_err());
        // 128 symbols flat → weights all 1 → RLE marker → direct OK
        let nb_bits = [7u8; 129];
        let mut out = Vec::new();
        let size = write_c_table(&mut out, &nb_bits, 128, 7).expect("write");
        assert_eq!(out[0] & 0x80, 0x80, "direct path chosen");
        assert_eq!(size, out.len());
        let wt = read_stats(&out).expect("read");
        assert_eq!(wt.nb_symbols, 129);
        // 128 explicit weight-1 + implied last weight 8 (Kraft 128·2^0 + 2^7
        // = 256 = 2^8)
        assert!(wt.weights[..128].iter().all(|&w| w == 1));
        assert_eq!(wt.weights[128], 8);
        assert_eq!(wt.table_log, 8);
    }
}
