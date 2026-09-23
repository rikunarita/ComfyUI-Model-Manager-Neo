//! FSE (Finite State Entropy / tANS) — the normalized-count table codec used
//! by huff0 weight headers (RFC 8878 §4.1.1, vendored `fse_compress.c` /
//! `fse_decompress.c` / `entropy_common.c`).
//!
//! Scope in this codebase: huff0 weight tables — alphabets ≤ 13 (weights
//! 0..=12), streams ≤ 127 bytes, `tableLog ≤ 6`
//! (`MAX_FSE_TABLELOG_FOR_HUFF_HEADER`). The decoder must accept every stream
//! the C encoder can emit and validate hostile input; the encoder mirrors the
//! C algorithms step for step (`normalize_count` incl. the `normalize_m2`
//! fallback, `write_n_count`, `build_c_table`, `compress_using_ctable` with
//! its dual-state interleaved writer) so weight headers are BYTE-IDENTICAL
//! to the C core's.
//!
//! Ported from the vendored sources on 2026-09-23; pointer arithmetic of the
//! C NCount reader is mirrored with isize indices and wrapping subtractions
//! (the C relies on size_t wraparound in two boundary conditions — the port
//! reproduces the branch outcomes, replaces its OOB reads with zero padding
//! and its UB shifts with saturating ones: hostile input errors out safely
//! instead of reading heap garbage).

use crate::bitstream::{BitReader, BitWriter, StreamStatus, highbit32};
use crate::{CodecError, CodecResult};

/// `FSE_MIN_TABLELOG` (fse.h L676).
pub const MIN_TABLELOG: u32 = 5;
/// `FSE_MAX_TABLELOG` = `FSE_MAX_MEMORY_USAGE(14) - 2` (fse.h L641/672).
pub const MAX_TABLELOG: u32 = 12;
/// `FSE_TABLELOG_ABSOLUTE_MAX` (fse.h L678).
pub const TABLELOG_ABSOLUTE_MAX: u32 = 15;
/// `FSE_DEFAULT_TABLELOG` = `FSE_DEFAULT_MEMORY_USAGE(13) - 2` (fse.h L644/675).
pub const DEFAULT_TABLELOG: u32 = 11;
/// Max tableLog of an FSE-compressed huff0 weight header
/// (`MAX_FSE_TABLELOG_FOR_HUFF_HEADER`, huf_compress.c).
pub const WEIGHT_HEADER_MAX_LOG: u32 = 6;

/// `FSE_optimalTableLog_internal` (fse_compress.c) — `minus` is 1 for huff0
/// (`HUF_optimalTableLog`) and 2 for plain FSE / weight compression.
/// `src_size` must be > 1 (callers guarantee; RLE is handled before).
#[must_use]
pub fn optimal_table_log(
    max_table_log: u32,
    src_size: usize,
    max_symbol_value: u32,
    minus: u32,
) -> u32 {
    // C computes in U32 with wrapping semantics: for src_size == 2,
    // highbit32(1) - 1 underflows to 0xFFFFFFFF — mirror exactly.
    let max_bits_src = highbit32((src_size - 1) as u32).wrapping_sub(minus);
    let min_bits_src = highbit32(src_size as u32) + 1;
    let min_bits_symbols = if max_symbol_value == 0 {
        2
    } else {
        highbit32(max_symbol_value) + 2
    };
    let min_bits = min_bits_src.min(min_bits_symbols);
    let mut table_log = if max_table_log == 0 {
        DEFAULT_TABLELOG
    } else {
        max_table_log
    };
    if max_bits_src < table_log {
        table_log = max_bits_src;
    }
    if min_bits > table_log {
        table_log = min_bits;
    }
    table_log.clamp(MIN_TABLELOG, MAX_TABLELOG)
}

/// One decoding-table cell (`FSE_decode_t`).
#[derive(Debug, Clone, Copy)]
pub struct DecodeCell {
    pub new_state: u16,
    pub symbol: u8,
    pub nb_bits: u8,
}

/// A built FSE decoding table (`FSE_DTable` without its header word).
#[derive(Debug, Clone)]
pub struct DTable {
    pub table_log: u32,
    #[allow(dead_code)] // consulted by C to pick the fast decoder; we always
    // use the safe path (identical outputs, nbBits>=0 safe)
    pub fast_mode: bool,
    pub cells: Vec<DecodeCell>,
}

/// `FSE_readNCount` (entropy_common.c): parse the normalized-count header.
/// Returns (norm, max_sv, table_log, bytes consumed).
///
/// # Errors
/// Any malformed bit pattern (C's corruption/tableLog errors), plus safe
/// handling of the boundary quirks documented in the module header.
pub fn read_n_count(src: &[u8], max_sv_limit: u32) -> CodecResult<(Vec<i16>, u32, u32, usize)> {
    // C: hbSize < 4 → pad into a 4-byte buffer and re-run, then reject when
    // the parse consumed more than the real length.
    if src.len() < 4 {
        let mut padded = [0u8; 4];
        padded[..src.len()].copy_from_slice(src);
        let (norm, max_sv, table_log, used) = read_n_count(&padded, max_sv_limit)?;
        if used > src.len() {
            return Err(CodecError::Corrupt(
                "FSE NCount longer than input".to_owned(),
            ));
        }
        return Ok((norm, max_sv, table_log, used));
    }

    let iend = src.len() as isize;
    let read_le32 = |at: isize| -> u32 {
        let mut b = [0u8; 4];
        if at >= 0 && (at as usize) < src.len() {
            let n = (src.len() - at as usize).min(4);
            b[..n].copy_from_slice(&src[at as usize..at as usize + n]);
        }
        u32::from_le_bytes(b)
    };

    let mut norm = vec![0i16; (max_sv_limit + 1) as usize];
    let mut ip: isize = 0;
    let mut bit_stream = read_le32(ip);
    let nb_bits0 = (bit_stream & 0xF) + MIN_TABLELOG;
    if nb_bits0 > TABLELOG_ABSOLUTE_MAX {
        return Err(CodecError::Fse(format!(
            "tableLog {nb_bits0} > absolute max"
        )));
    }
    bit_stream >>= 4;
    let mut bit_count: i32 = 4;
    let table_log = nb_bits0;
    let mut remaining: i32 = (1i32 << nb_bits0) + 1;
    let mut threshold: i32 = 1i32 << nb_bits0;
    let mut nb_bits = nb_bits0 as i32 + 1;
    let mut char_num = 0u32;
    let mut previous0 = false;
    let max_sv = max_sv_limit;

    // C's boundary comparisons use size_t wraparound (iend-5 / iend-7 can
    // underflow for tiny buffers) — isize arithmetic reproduces the branch
    // outcomes without wrapping surprises.
    while remaining > 1 && char_num <= max_sv {
        if previous0 {
            let mut n0 = char_num;
            while (bit_stream & 0xFFFF) == 0xFFFF {
                n0 += 24;
                if ip < iend - 5 {
                    ip += 2;
                    bit_stream = read_le32(ip).checked_shr(bit_count as u32).unwrap_or(0);
                } else {
                    bit_stream >>= 16;
                    bit_count += 16;
                }
            }
            while (bit_stream & 3) == 3 {
                n0 += 3;
                bit_stream >>= 2;
                bit_count += 2;
            }
            n0 += bit_stream & 3;
            bit_count += 2;
            if n0 > max_sv {
                return Err(CodecError::Fse(format!(
                    "NCount zero-run beyond maxSymbolValue ({n0} > {max_sv})"
                )));
            }
            while char_num < n0 {
                norm[char_num as usize] = 0;
                char_num += 1;
            }
            let shifted = ip + (bit_count >> 3) as isize;
            if ip <= iend - 7 || shifted <= iend - 4 {
                debug_assert!((bit_count >> 3) <= 3);
                ip = shifted.max(0);
                bit_count &= 7;
                bit_stream = read_le32(ip).checked_shr(bit_count as u32).unwrap_or(0);
            } else {
                bit_stream >>= 2;
            }
        }
        {
            let max = (2 * threshold - 1) - remaining;
            let count: i32;
            if (bit_stream & (threshold - 1) as u32) < max as u32 {
                count = (bit_stream & (threshold - 1) as u32) as i32;
                bit_count += nb_bits - 1;
            } else {
                let mut c = (bit_stream & (2 * threshold - 1) as u32) as i32;
                if c >= threshold {
                    c -= max;
                }
                count = c;
                bit_count += nb_bits;
            }
            let count = count - 1; // extra accuracy: -1 means +1
            remaining -= count.abs();
            if char_num > max_sv {
                return Err(CodecError::Fse("NCount symbol overflow".to_owned()));
            }
            norm[char_num as usize] = count as i16;
            char_num += 1;
            previous0 = count == 0;
            while remaining < threshold {
                nb_bits -= 1;
                threshold >>= 1;
            }
            let shifted = ip + (bit_count >> 3) as isize;
            if ip <= iend - 7 || shifted <= iend - 4 {
                ip = shifted.max(0);
                bit_count &= 7;
            } else {
                bit_count -= (8 * (iend - 4 - ip)) as i32;
                ip = iend - 4;
            }
            bit_stream = read_le32(ip)
                .checked_shr((bit_count & 31) as u32)
                .unwrap_or(0);
        }
    }
    if remaining != 1 {
        return Err(CodecError::Corrupt(format!(
            "FSE NCount probabilities invalid (remaining={remaining})"
        )));
    }
    if bit_count > 32 {
        return Err(CodecError::Corrupt("FSE NCount bit overflow".to_owned()));
    }
    let out_max_sv = char_num
        .checked_sub(1)
        .ok_or_else(|| CodecError::Corrupt("empty FSE NCount".to_owned()))?;
    ip += ((bit_count + 7) >> 3) as isize;
    norm.truncate(out_max_sv as usize + 1);
    Ok((norm, out_max_sv, table_log, ip.max(0) as usize))
}

/// `FSE_buildDTable` (fse_decompress.c).
///
/// # Errors
/// Invalid normalized counts (the spread must visit every cell exactly once).
pub fn build_d_table(norm: &[i16], max_sv: u32, table_log: u32) -> CodecResult<DTable> {
    if table_log > MAX_TABLELOG {
        return Err(CodecError::Fse(format!(
            "tableLog {table_log} > {MAX_TABLELOG}"
        )));
    }
    if max_sv as usize >= norm.len() {
        return Err(CodecError::Fse("maxSymbolValue beyond counts".to_owned()));
    }
    let table_size = 1usize << table_log;
    let mut cells = vec![
        DecodeCell {
            new_state: 0,
            symbol: 0,
            nb_bits: 0
        };
        table_size
    ];
    let mut symbol_next = vec![0u16; (max_sv + 1) as usize];
    let mut fast_mode = true;
    let large_limit = 1i32 << (table_log - 1);
    let mut high_threshold = table_size - 1;
    for s in 0..=max_sv as usize {
        let n = i32::from(norm[s]);
        if n == -1 {
            cells[high_threshold].symbol = s as u8;
            high_threshold = high_threshold.wrapping_sub(1);
            symbol_next[s] = 1;
        } else {
            if n >= large_limit {
                fast_mode = false;
            }
            if n < 0 {
                return Err(CodecError::Fse(format!("invalid normalized count {n}")));
            }
            symbol_next[s] = n as u16;
        }
    }
    // Spread symbols (deterministic FSE placement, FSE_TABLESTEP).
    let table_mask = table_size - 1;
    let step = (table_size >> 1) + (table_size >> 3) + 3;
    let mut position = 0usize;
    for (s, &cnt) in norm.iter().enumerate().take(max_sv as usize + 1) {
        for _ in 0..cnt {
            cells[position].symbol = s as u8;
            position = (position + step) & table_mask;
            while position > high_threshold && high_threshold < table_size {
                position = (position + step) & table_mask;
            }
        }
    }
    if position != 0 {
        return Err(CodecError::Corrupt(
            "FSE normalized counts do not fill the table exactly once".to_owned(),
        ));
    }
    // Build decoding transitions.
    for cell in cells.iter_mut() {
        let symbol = cell.symbol as usize;
        let next_state = u32::from(symbol_next[symbol]);
        symbol_next[symbol] += 1;
        let nb = table_log - highbit32(next_state);
        cell.nb_bits = nb as u8;
        cell.new_state = ((next_state << nb) - table_size as u32) as u16;
    }
    Ok(DTable {
        table_log,
        fast_mode,
        cells,
    })
}

/// `FSE_decompress_usingDTable_generic` — the dual-state decode loop
/// (always the non-fast variant: identical output, and it tolerates the
/// nbBits==0 cells the fast C path must exclude via fastMode).
///
/// # Errors
/// Corrupt stream or output exceeding `out.len()`.
pub fn decompress_using_d_table(dt: &DTable, src: &[u8], out: &mut [u8]) -> CodecResult<usize> {
    let omax = out.len();
    let mut bit_d = BitReader::init(src)?;
    let mut state1 = dt.read_state(&mut bit_d)?;
    let mut state2 = dt.read_state(&mut bit_d)?;

    let mut op = 0usize;
    let olimit = omax.saturating_sub(3);
    while bit_d.reload() == StreamStatus::Unfinished && op < olimit {
        out[op] = dt.decode_symbol(&mut bit_d, &mut state1)?;
        out[op + 1] = dt.decode_symbol(&mut bit_d, &mut state2)?;
        out[op + 2] = dt.decode_symbol(&mut bit_d, &mut state1)?;
        out[op + 3] = dt.decode_symbol(&mut bit_d, &mut state2)?;
        op += 4;
    }
    // Tail: C's `while(1)` with the two overflow breaks and the omax-2 guard.
    loop {
        if op > omax.saturating_sub(2) {
            return Err(CodecError::Size(
                "FSE output overflow (dstSize_tooSmall)".to_owned(),
            ));
        }
        out[op] = dt.decode_symbol(&mut bit_d, &mut state1)?;
        op += 1;
        if bit_d.reload() == StreamStatus::Overflow {
            if op >= omax {
                return Err(CodecError::Size("FSE output overflow".to_owned()));
            }
            out[op] = dt.decode_symbol(&mut bit_d, &mut state2)?;
            op += 1;
            break;
        }
        if op > omax.saturating_sub(2) {
            return Err(CodecError::Size(
                "FSE output overflow (dstSize_tooSmall)".to_owned(),
            ));
        }
        out[op] = dt.decode_symbol(&mut bit_d, &mut state2)?;
        op += 1;
        if bit_d.reload() == StreamStatus::Overflow {
            if op >= omax {
                return Err(CodecError::Size("FSE output overflow".to_owned()));
            }
            out[op] = dt.decode_symbol(&mut bit_d, &mut state1)?;
            op += 1;
            break;
        }
    }
    Ok(op)
}

impl DTable {
    /// `FSE_initDState`: the initial state is tableLog bits, MSB-first from
    /// the backward reader.
    fn read_state(&self, bit_d: &mut BitReader<'_>) -> CodecResult<usize> {
        let s = bit_d.read_bits(self.table_log) as usize;
        let _ = bit_d.reload();
        if s >= self.cells.len() {
            return Err(CodecError::Corrupt(
                "FSE initial state out of table".to_owned(),
            ));
        }
        Ok(s)
    }

    /// `FSE_decodeSymbol` (non-fast): emit the symbol, consume nbBits,
    /// transition the state.
    fn decode_symbol(&self, bit_d: &mut BitReader<'_>, state: &mut usize) -> CodecResult<u8> {
        let cell = *self
            .cells
            .get(*state)
            .ok_or_else(|| CodecError::Corrupt("FSE state out of table".to_owned()))?;
        let low = bit_d.read_bits(u32::from(cell.nb_bits));
        *state = usize::from(cell.new_state) + low as usize;
        Ok(cell.symbol)
    }
}

/// `FSE_decompress_wksp` — the exact entry point `HUF_readStats` uses for
/// FSE-compressed weight tables.
///
/// # Errors
/// Any malformed input (propagated).
pub fn decompress(src: &[u8], max_dst: usize, max_log: u32) -> CodecResult<Vec<u8>> {
    let (norm, max_sv, table_log, used) = read_n_count(src, 255)?;
    if table_log > max_log {
        return Err(CodecError::Fse(format!(
            "weight-table tableLog {table_log} > {max_log}"
        )));
    }
    if used > src.len() {
        return Err(CodecError::Corrupt("FSE NCount beyond input".to_owned()));
    }
    let dt = build_d_table(&norm, max_sv, table_log)?;
    let mut out = vec![0u8; max_dst];
    let n = decompress_using_d_table(&dt, &src[used..], &mut out)?;
    out.truncate(n);
    Ok(out)
}

// ---------------------------------------------------------------------------
// Encoder side (huff0 weight tables) — byte-exact mirror of fse_compress.c
// ---------------------------------------------------------------------------

/// `FSE_normalizeCount` (+ the `FSE_normalizeM2` corner-case fallback).
/// Returns `None` for the RLE case (some symbol has count == total; C
/// returns 0 there and `HUF_compressWeights` falls back to direct weights).
///
/// # Errors
/// `table_log` outside [MIN, MAX], below the distribution minimum, or
/// `total < 2` (callers must handle RLE/single-symbol inputs first).
pub fn normalize_count(
    count: &[u32],
    total: usize,
    max_sv: u32,
    table_log: u32,
) -> CodecResult<Option<(Vec<i16>, u32)>> {
    if total < 2 {
        return Err(CodecError::Size(
            "FSE normalize needs total >= 2 (RLE handled by caller)".to_owned(),
        ));
    }
    let table_log = if table_log == 0 {
        DEFAULT_TABLELOG
    } else {
        table_log
    };
    if !(MIN_TABLELOG..=MAX_TABLELOG).contains(&table_log) {
        return Err(CodecError::Fse(format!(
            "tableLog {table_log} outside [{MIN_TABLELOG},{MAX_TABLELOG}]"
        )));
    }
    let min_log = {
        let min_bits_src = highbit32(total as u32) + 1;
        let min_bits_symbols = if max_sv == 0 {
            2
        } else {
            highbit32(max_sv) + 2
        };
        min_bits_src.min(min_bits_symbols)
    };
    if table_log < min_log {
        return Err(CodecError::Fse(
            "tableLog too small for the distribution".to_owned(),
        ));
    }

    const RTB_TABLE: [u32; 8] = [0, 473195, 504333, 520860, 550000, 700000, 750000, 830000];
    let mut norm = vec![0i16; (max_sv + 1) as usize];
    let scale = 62u32 - table_log;
    let step: u64 = (1u64 << 62) / total as u64; // the one division
    let v_step: u64 = 1u64 << (scale - 20);
    let mut still_to_distribute: i32 = 1i32 << table_log;
    let mut largest: usize = 0;
    let mut largest_p: i16 = 0;
    let low_threshold = (total >> table_log) as u32;

    for s in 0..=max_sv as usize {
        let c = count[s];
        if c as usize == total {
            return Ok(None); // RLE special case (C returns 0)
        }
        if c == 0 {
            norm[s] = 0;
            continue;
        }
        if c <= low_threshold {
            norm[s] = -1;
            still_to_distribute -= 1;
        } else {
            let scaled = u64::from(c) * step;
            let mut proba = ((scaled >> scale) & 0x7FFF) as i16;
            if proba < 8 {
                let rest_to_beat = v_step * u64::from(RTB_TABLE[proba as usize]);
                let frac = scaled.wrapping_sub(u64::from(proba as u16) << scale);
                if frac > rest_to_beat {
                    proba += 1;
                }
            }
            if proba > largest_p {
                largest_p = proba;
                largest = s;
            }
            norm[s] = proba;
            still_to_distribute -= i32::from(proba);
        }
    }
    if -still_to_distribute >= i32::from(norm[largest] >> 1) {
        normalize_m2(&mut norm, table_log, count, total, max_sv)?;
    } else {
        norm[largest] = (i32::from(norm[largest]) + still_to_distribute) as i16;
    }
    Ok(Some((norm, table_log)))
}

/// `FSE_normalizeM2` — the secondary normalization for corner distributions.
fn normalize_m2(
    norm: &mut [i16],
    table_log: u32,
    count: &[u32],
    total: usize,
    max_sv: u32,
) -> CodecResult<()> {
    const NOT_YET_ASSIGNED: i16 = -2;
    let mut total = total as u64;
    let low_threshold = (total >> table_log) as u32;
    let mut low_one = ((total * 3) >> (table_log + 1)) as u32;
    let mut distributed = 0u32;

    for s in 0..=max_sv as usize {
        if count[s] == 0 {
            norm[s] = 0;
            continue;
        }
        if count[s] <= low_threshold {
            norm[s] = -1;
            distributed += 1;
            total -= u64::from(count[s]);
            continue;
        }
        if count[s] <= low_one {
            norm[s] = 1;
            distributed += 1;
            total -= u64::from(count[s]);
            continue;
        }
        norm[s] = NOT_YET_ASSIGNED;
    }
    let mut to_distribute = (1u32 << table_log) - distributed;
    if to_distribute == 0 {
        return Ok(());
    }
    if total / u64::from(to_distribute) > u64::from(low_one) {
        low_one = ((total * 3) / (u64::from(to_distribute) * 2)) as u32;
        for s in 0..=max_sv as usize {
            if norm[s] == NOT_YET_ASSIGNED && count[s] <= low_one {
                norm[s] = 1;
                distributed += 1;
                total -= u64::from(count[s]);
            }
        }
        to_distribute = (1u32 << table_log) - distributed;
    }
    if distributed == max_sv + 1 {
        // every symbol is "poor": give all remaining states to the largest
        let mut max_v = 0usize;
        let mut max_c = 0u32;
        for (s, &c) in count.iter().enumerate().take(max_sv as usize + 1) {
            if c > max_c {
                max_v = s;
                max_c = c;
            }
        }
        norm[max_v] = (i32::from(norm[max_v]) + to_distribute as i32) as i16;
        return Ok(());
    }
    if total == 0 {
        let mut s = 0usize;
        let mut guard = 0u32;
        while to_distribute > 0 {
            if norm[s] > 0 {
                to_distribute -= 1;
                norm[s] += 1;
            }
            s = (s + 1) % (max_sv as usize + 1);
            guard += 1;
            if guard > 1_000_000 {
                return Err(CodecError::Fse(
                    "normalizeM2 distribution loop stuck".to_owned(),
                ));
            }
        }
        return Ok(());
    }
    let v_step_log = 62u32 - table_log;
    let mid = (1u64 << (v_step_log - 1)) - 1;
    let r_step = (((1u64 << v_step_log) * u64::from(to_distribute)) + mid) / total;
    let mut tmp_total = mid;
    for s in 0..=max_sv as usize {
        if norm[s] == NOT_YET_ASSIGNED {
            let end = tmp_total + u64::from(count[s]) * r_step;
            let s_start = (tmp_total >> v_step_log) as u32;
            let s_end = (end >> v_step_log) as u32;
            let weight = s_end - s_start;
            if weight < 1 {
                return Err(CodecError::Fse(
                    "normalizeM2 zero weight (incompressible)".to_owned(),
                ));
            }
            norm[s] = weight as i16;
            tmp_total = end;
        }
    }
    Ok(())
}

/// `FSE_writeNCount_generic` — serialize normalized counts (RFC 8878 §4.1.1
/// bit layout). Byte-identical to the C writer (same LSB-first bitStream,
/// same 24-zero/3-zero run encodings, same final partial flush).
///
/// # Errors
/// Distribution that does not sum to the table size.
pub fn write_n_count(
    out: &mut Vec<u8>,
    norm: &[i16],
    max_sv: u32,
    table_log: u32,
) -> CodecResult<usize> {
    if !(MIN_TABLELOG..=MAX_TABLELOG).contains(&table_log) {
        return Err(CodecError::Fse(
            "writeNCount tableLog out of range".to_owned(),
        ));
    }
    let start_len = out.len();
    let alphabet_size = max_sv + 1;
    let mut bit_stream: u32 = (table_log - MIN_TABLELOG) & 0xF;
    let mut bit_count: i32 = 4;
    let table_size: i32 = 1i32 << table_log;
    let mut remaining: i32 = table_size + 1;
    let mut threshold: i32 = table_size;
    let mut nb_bits = table_log as i32 + 1;
    let mut symbol = 0u32;
    let mut previous_is0 = false;

    macro_rules! flush2 {
        () => {
            out.push((bit_stream & 0xFF) as u8);
            out.push((bit_stream >> 8) as u8);
            bit_stream >>= 16;
            bit_count -= 16;
        };
    }

    while symbol < alphabet_size && remaining > 1 {
        if previous_is0 {
            let mut start = symbol;
            while symbol < alphabet_size && norm[symbol as usize] == 0 {
                symbol += 1;
            }
            if symbol == alphabet_size {
                break; // C: "incorrect distribution" tolerated as end
            }
            while symbol >= start + 24 {
                start += 24;
                bit_stream = bit_stream.wrapping_add(0xFFFFu32 << bit_count);
                out.push((bit_stream & 0xFF) as u8);
                out.push((bit_stream >> 8) as u8);
                bit_stream >>= 16;
                // NOTE: bit_count is deliberately NOT adjusted here — the C
                // writer emitted 16 bits and kept the same pending-bit count
                // (the shifted-in ones are the marker's high bits).
            }
            while symbol >= start + 3 {
                start += 3;
                bit_stream = bit_stream.wrapping_add(3u32 << bit_count);
                bit_count += 2;
            }
            bit_stream = bit_stream.wrapping_add((symbol - start) << bit_count);
            bit_count += 2;
            if bit_count > 16 {
                flush2!();
            }
        }
        {
            let mut count = i32::from(norm[symbol as usize]);
            symbol += 1;
            let max = (2 * threshold - 1) - remaining;
            remaining -= count.abs();
            count += 1; // extra accuracy
            if count >= threshold {
                count += max;
            }
            bit_stream = bit_stream.wrapping_add((count as u32) << bit_count);
            bit_count += nb_bits;
            bit_count -= i32::from(count < max);
            previous_is0 = count == 1;
            if remaining < 1 {
                return Err(CodecError::Fse(
                    "writeNCount distribution underflow".to_owned(),
                ));
            }
            while remaining < threshold {
                nb_bits -= 1;
                threshold >>= 1;
            }
        }
        if bit_count > 16 {
            flush2!();
        }
    }
    if remaining != 1 {
        return Err(CodecError::Fse(
            "writeNCount distribution does not sum".to_owned(),
        ));
    }
    // Final flush: C writes 2 bytes and advances (bitCount+7)/8 of them.
    out.push((bit_stream & 0xFF) as u8);
    out.push(((bit_stream >> 8) & 0xFF) as u8);
    let advance = ((bit_count + 7) / 8).max(0) as usize;
    let full = out.len() - start_len; // includes the 2 flush bytes
    out.truncate(start_len + full - 2 + advance.min(2));
    Ok(out.len() - start_len)
}

/// The encoder-side symbol transform (`FSE_symbolCompressionTransform`).
#[derive(Debug, Clone, Copy)]
pub struct SymbolTT {
    pub delta_nb_bits: u32,
    pub delta_find_state: i32,
}

/// The encoder-side C table (`FSE_buildCTable_wksp` products only — the
/// state table + per-symbol transforms; the C header word is not needed).
#[derive(Debug, Clone)]
pub struct CTable {
    pub table_log: u32,
    pub max_sv: u32,
    /// `tableU16`: state table, sorted by symbol (values tableSize+u).
    pub state_table: Vec<u16>,
    pub symbol_tt: Vec<SymbolTT>,
}

/// `FSE_buildCTable_wksp` (fse_compress.c) — the state table and symbol
/// transforms used by [`compress_using_ctable`].
///
/// # Errors
/// Counts that do not fill the table exactly once.
pub fn build_c_table(norm: &[i16], max_sv: u32, table_log: u32) -> CodecResult<CTable> {
    let table_size = 1usize << table_log;
    let step = (table_size >> 1) + (table_size >> 3) + 3;
    let mut cumul = vec![0u32; (max_sv + 2) as usize];
    let mut table_symbol = vec![0u8; table_size];
    let mut high_threshold = table_size - 1;

    for u in 1..=(max_sv + 1) as usize {
        if norm[u - 1] == -1 {
            cumul[u] = cumul[u - 1] + 1;
            table_symbol[high_threshold] = (u - 1) as u8;
            high_threshold = high_threshold.wrapping_sub(1);
        } else {
            if norm[u - 1] < 0 {
                return Err(CodecError::Fse(format!(
                    "invalid normalized count {}",
                    norm[u - 1]
                )));
            }
            cumul[u] = cumul[u - 1] + norm[u - 1] as u32;
        }
    }
    cumul[(max_sv + 1) as usize] = table_size as u32 + 1;

    let mut position = 0usize;
    for (symbol, &cnt) in norm.iter().enumerate().take(max_sv as usize + 1) {
        for _ in 0..cnt {
            table_symbol[position] = symbol as u8;
            position = (position + step) & (table_size - 1);
            while position > high_threshold && high_threshold < table_size {
                position = (position + step) & (table_size - 1);
            }
        }
    }
    if position != 0 {
        return Err(CodecError::Fse(
            "CTable spread did not fill the table".to_owned(),
        ));
    }

    // Build table: state values sorted by symbol order.
    let mut state_table = vec![0u16; table_size];
    let mut cumul = cumul.clone();
    for (u, &sym) in table_symbol.iter().enumerate() {
        let s = sym as usize;
        state_table[cumul[s] as usize] = (table_size + u) as u16;
        cumul[s] += 1;
    }

    // Symbol transformation table.
    let mut symbol_tt = vec![
        SymbolTT {
            delta_nb_bits: 0,
            delta_find_state: 0
        };
        (max_sv + 1) as usize
    ];
    let mut total = 0u32;
    for s in 0..=max_sv as usize {
        match norm[s] {
            0 => {
                symbol_tt[s].delta_nb_bits = ((table_log + 1) << 16).wrapping_sub(1 << table_log);
            }
            -1 | 1 => {
                symbol_tt[s].delta_nb_bits = (table_log << 16).wrapping_sub(1 << table_log);
                symbol_tt[s].delta_find_state = total as i32 - 1;
                total += 1;
            }
            n => {
                let n = n as u32;
                let max_bits_out = table_log - highbit32(n - 1);
                let min_state_plus = n << max_bits_out;
                symbol_tt[s].delta_nb_bits = (max_bits_out << 16).wrapping_sub(min_state_plus);
                symbol_tt[s].delta_find_state = total as i32 - n as i32;
                total += n;
            }
        }
    }
    Ok(CTable {
        table_log,
        max_sv,
        state_table,
        symbol_tt,
    })
}

/// One compression state (`FSE_CState_t`).
struct CState {
    value: u32,
}

impl CTable {
    /// `FSE_initCState2`.
    fn init_state(&self, symbol: u8) -> CodecResult<CState> {
        let tt = self
            .symbol_tt
            .get(symbol as usize)
            .ok_or_else(|| CodecError::Fse("symbol beyond CTable alphabet".to_owned()))?;
        let nb_bits_out = (tt.delta_nb_bits.wrapping_add(1 << 15)) >> 16;
        let value = (nb_bits_out << 16).wrapping_sub(tt.delta_nb_bits);
        let idx = (value >> nb_bits_out) as i32 + tt.delta_find_state;
        let state = *self
            .state_table
            .get(idx as usize)
            .ok_or_else(|| CodecError::Fse("initCState index out of table".to_owned()))?;
        Ok(CState {
            value: u32::from(state),
        })
    }

    /// `FSE_encodeSymbol`.
    fn encode_symbol(&self, w: &mut BitWriter, state: &mut CState, symbol: u8) -> CodecResult<()> {
        let tt = self
            .symbol_tt
            .get(symbol as usize)
            .ok_or_else(|| CodecError::Fse("symbol beyond CTable alphabet".to_owned()))?;
        let nb_bits_out = (state.value.wrapping_add(tt.delta_nb_bits)) >> 16;
        w.add_bits(u64::from(state.value), nb_bits_out);
        let idx = (state.value >> nb_bits_out) as i32 + tt.delta_find_state;
        state.value = u32::from(
            *self
                .state_table
                .get(idx as usize)
                .ok_or_else(|| CodecError::Fse("encodeSymbol index out of table".to_owned()))?,
        );
        Ok(())
    }

    /// `FSE_flushCState`.
    fn flush_state(&self, w: &mut BitWriter, state: &CState) {
        w.add_bits(u64::from(state.value), self.table_log);
        w.flush_bits();
    }
}

/// `FSE_compress_usingCTable` (+ `_generic`): the dual-state backward writer.
/// Returns the compressed size, or `None` when incompressible/overflow (C
/// returns 0). `dst_capacity` mirrors the C `dstSize` (the writer refuses
/// streams that would not fit — same rule via [`BitWriter`]).
///
/// # Errors
/// Only for symbols outside the table alphabet (logic bug guards).
pub fn compress_using_ctable(
    ct: &CTable,
    src: &[u8],
    dst_capacity: usize,
) -> CodecResult<Option<Vec<u8>>> {
    if src.len() <= 2 {
        return Ok(None); // C: `srcSize <= 2 → 0`
    }
    // C: fast = dstSize >= FSE_BLOCKBOUND(srcSize) → flushBitsFast
    let block_bound = src.len() + (src.len() >> 7) + 4 + 8;
    let fast = dst_capacity >= block_bound;
    let mut w = match BitWriter::new(dst_capacity) {
        Ok(w) => w,
        Err(_) => return Ok(None), // dstSize <= 8: C's initCStream error → 0
    };

    let mut ip = src.len();
    let mut state1;
    let mut state2;
    if src.len() & 1 == 1 {
        ip -= 1;
        state1 = ct.init_state(src[ip])?;
        ip -= 1;
        state2 = ct.init_state(src[ip])?;
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state1, src[ip])?;
        if fast {
            w.flush_bits_fast();
        } else {
            w.flush_bits();
        }
    } else {
        ip -= 1;
        state2 = ct.init_state(src[ip])?;
        ip -= 1;
        state1 = ct.init_state(src[ip])?;
    }

    // "join to mod 4" — on 64-bit containers (64 > 12*4+7) the C runs the
    // bit-2 test; mirror it exactly.
    let mut remaining = src.len() - 2;
    if remaining & 2 != 0 {
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state2, src[ip])?;
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state1, src[ip])?;
        if fast {
            w.flush_bits_fast();
        } else {
            w.flush_bits();
        }
        remaining -= 2;
    }
    let _ = remaining;

    while ip > 0 {
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state2, src[ip])?;
        // (64 < 12*2+7) is false on 64-bit → no mid flush (C static test)
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state1, src[ip])?;
        // (64 > 12*4+7) is true on 64-bit → two more symbols per loop
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state2, src[ip])?;
        ip -= 1;
        ct.encode_symbol(&mut w, &mut state1, src[ip])?;
        if fast {
            w.flush_bits_fast();
        } else {
            w.flush_bits();
        }
    }

    ct.flush_state(&mut w, &state2);
    ct.flush_state(&mut w, &state1);
    Ok(w.close())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Round-trip the whole encoder→decoder chain over many weight-like
    /// distributions (the real use: histograms of huff0 weights 0..=12).
    fn roundtrip_norm(count_full: &[u32], table_log: u32) {
        // Real callers (HIST_count) always report maxSV = the largest
        // PRESENT symbol; trailing-zero alphabets do not occur. writeNCount
        // (like the C) stops once all probability mass is written, so the
        // decoder legitimately recovers a smaller maxSV for padded inputs —
        // trim to model the real flow.
        let mut count_v = count_full.to_vec();
        while count_v.len() > 1 && *count_v.last().unwrap() == 0 {
            count_v.pop();
        }
        let count: &[u32] = &count_v;
        let total: usize = count.iter().map(|&c| c as usize).sum();
        let max_sv = (count.len() - 1) as u32;
        let (norm, log) = match normalize_count(count, total, max_sv, table_log).expect("normalize")
        {
            Some(v) => v,
            None => return, // RLE case: caller falls back, nothing to test
        };
        let mut buf = Vec::new();
        write_n_count(&mut buf, &norm, max_sv, log).expect("writeNCount");
        // decode
        let (norm2, max_sv2, log2, used) = read_n_count(&buf, 255).expect("readNCount");
        assert_eq!(used, buf.len(), "NCount must be consumed exactly");
        assert_eq!(log2, log);
        assert_eq!(max_sv2, max_sv);
        assert_eq!(norm2, norm);
        // build both tables and decode an FSE-compressed payload
        let dt = build_d_table(&norm2, max_sv2, log2).expect("buildDTable");
        let ct = build_c_table(&norm, max_sv, log).expect("buildCTable");
        // fabricate a payload from symbols that actually occur (norm>0 —
        // zero-probability symbols are not encodable, mirroring C where the
        // weight array only ever contains present symbols)
        let mut payload_src = Vec::new();
        for (s, &c) in count.iter().enumerate() {
            if s as u32 <= max_sv && c > 0 {
                for _ in 0..c.min(7) {
                    payload_src.push(s as u8);
                }
            }
        }
        if payload_src.len() >= 3 {
            let comp = compress_using_ctable(&ct, &payload_src, payload_src.len() + 64)
                .expect("compress")
                .expect("fits");
            let mut out = vec![0u8; payload_src.len() + 3];
            let n = decompress_using_d_table(&dt, &comp, &mut out).expect("decompress");
            assert_eq!(&out[..n], &payload_src[..], "FSE payload roundtrip");
        }
    }

    #[test]
    fn weight_like_distributions_roundtrip() {
        // typical huff0 weight histograms (alphabet ≤ 13)
        roundtrip_norm(&[3, 5, 4, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0], 6);
        roundtrip_norm(&[1, 1], 5);
        roundtrip_norm(&[60, 30, 15, 8, 4, 2, 1, 1], 6);
        roundtrip_norm(&[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 6);
        roundtrip_norm(&[2, 1], 5);
        roundtrip_norm(&[200, 40, 10, 5, 1], 6);
        roundtrip_norm(&[2, 2, 2, 2], 5);
        roundtrip_norm(&[7, 5, 3, 1, 1, 1], 6);
        roundtrip_norm(&[1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1], 6);
        roundtrip_norm(&[1, 1, 0, 0, 1, 1], 5);
    }

    #[test]
    fn rle_and_edge_cases() {
        // RLE → None
        assert!(normalize_count(&[0, 64], 64, 1, 6).unwrap().is_none());
        // total < 2 → error, not panic
        assert!(normalize_count(&[1], 1, 0, 6).is_err());
    }

    #[test]
    fn optimal_table_log_matches_c_formula() {
        // Hand-computed from the C formula for representative sizes:
        // srcSize=262144 (256 KiB): highbit(262143)=17 → maxBitsSrc=16;
        // minBits=min(highbit(262144)+1=19, highbit(255)+2=9)=9 →
        // tableLog=min(11,16)... 11 stays (maxBitsSrc 16 > 11); minBits 9 < 11
        // → 11.
        assert_eq!(optimal_table_log(11, 262_144, 255, 1), 11);
        // srcSize=64: highbit(63)=5 → maxBitsSrc=4; minBits=min(7, 10)=7 →
        // tableLog=max(4→ then minBits 7) = 7 → clamp [5,12] → 7
        assert_eq!(optimal_table_log(11, 64, 255, 1), 7);
        // srcSize=16: highbit(15)=3 → maxBits=2; minBits=min(5,10)=5 → 5
        assert_eq!(optimal_table_log(11, 16, 255, 1), 5);
        // srcSize=2 (C underflow path): maxBitsSrc=0xFFFFFFFF → tableLog 11;
        // minBits=min(highbit(2)+1=2, highbit(maxSV)+2); maxSV=1 → 2+... =
        // highbit(1)+2 = 2 → minBits=2 → stays 11 → clamp → 11
        assert_eq!(optimal_table_log(11, 2, 1, 1), 11);
        // weights path: maxTableLog=6, minus=2, wtSize=8, maxSV=3:
        // maxBitsSrc=highbit(7)-2=0; minBits=min(highbit(8)+1=4, highbit(3)+2=3)=3
        // → tableLog = max(min(6→0), 3) = 3 → clamp min 5 → 5
        assert_eq!(optimal_table_log(6, 8, 3, 2), 5);
    }

    #[test]
    fn read_n_count_rejects_garbage() {
        for bad in [
            vec![0xFF; 4],                // tableLog nibble = 15+5 → too large
            vec![0x00, 0x00, 0x00, 0x00], // remaining never reaches 1
            vec![0x01],                   // too short + bad
            vec![],                       // empty
        ] {
            let r = read_n_count(&bad, 255);
            assert!(r.is_err() || r.unwrap().3 <= bad.len(), "input {bad:?}");
        }
    }

    #[test]
    fn decompress_rejects_garbage_safely() {
        for bad in [vec![0u8; 1], vec![0xFF; 8], vec![0x20, 0x21, 0x22, 0x23]] {
            let _ = decompress(&bad, 255, WEIGHT_HEADER_MAX_LOG); // must not panic
        }
    }
}
