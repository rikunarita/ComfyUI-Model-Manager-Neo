//! The FSE/huff0 bitstream primitives — a faithful mirror of the vendored
//! `bitstream.h` (FiniteStateEntropy), whose semantics RFC 8878 §4.1/§4.2
//! documents: streams are written FORWARD (LSB-first into a 64-bit container,
//! little-endian flushes, closed with a sentinel `1` bit + zero padding) and
//! read BACKWARD (the reader locates the sentinel in the last byte and
//! consumes bits from the top of a sliding 64-bit window).
//!
//! Writer byte output is BIT-IDENTICAL to `BIT_*CStream` for the same
//! add/flush call sequence (the encoder relies on that for byte-exact
//! golden parity with the C core — Plan §4.5-5 lets us relax this, but
//! exactness makes L2 diffing trivial).
//!
//! The reader mirrors `BIT_DStream_t` exactly, including the small-stream
//! (<8 bytes) container construction and the four reload states
//! (unfinished / end-of-buffer / completed / overflow), with bounds-checked
//! reads instead of the C pointer arithmetic (Plan §4.4.2: hostile input
//! must produce errors, never OOB).

use crate::{CodecError, CodecResult};

/// `BIT_highbit32`: index of the highest set bit (val must be != 0).
#[must_use]
pub const fn highbit32(val: u32) -> u32 {
    31 - val.leading_zeros()
}

// ---------------------------------------------------------------------------
// Writer (BIT_CStream_t)
// ---------------------------------------------------------------------------

/// Forward bit writer with the exact flush semantics of `BIT_CStream_t`.
///
/// `capacity` mirrors the C `dstCapacity`: the writer refuses (returns
/// `None` from [`close`]) when the stream would reach `capacity - 8`, the
/// same overflow rule as `BIT_closeCStream`.
pub struct BitWriter {
    buf: Vec<u8>,
    /// C `bitContainer`.
    container: u64,
    /// C `bitPos` — number of valid bits in `container`.
    bit_pos: u32,
    /// C `ptr - startPtr`.
    pos: usize,
    /// C `endPtr - startPtr` = capacity - 8 (saturating).
    end: usize,
    overflowed: bool,
}

impl BitWriter {
    /// Allocating constructor (tests, fuzz, one-shot callers).
    ///
    /// # Errors
    /// Capacity must exceed the 8-byte container (C `BIT_initCStream`).
    pub fn new(capacity: usize) -> CodecResult<Self> {
        Self::with_buf(Vec::new(), capacity)
    }

    /// Scratch-reusing constructor: `buf` is resized (NOT re-zeroed beyond
    /// growth — flushes overwrite everything they touch before `close`
    /// reports the size) and handed back by [`close`] for recycling.
    ///
    /// # Errors
    /// Capacity must exceed the 8-byte container.
    pub fn with_buf(mut buf: Vec<u8>, capacity: usize) -> CodecResult<Self> {
        if capacity <= 8 {
            return Err(CodecError::Size(format!(
                "bitstream destination too small ({capacity} <= 8)"
            )));
        }
        buf.resize(capacity + 8, 0); // headroom for the 8-byte LE flushes
        Ok(Self {
            buf,
            container: 0,
            bit_pos: 0,
            pos: 0,
            end: capacity - 8,
            overflowed: false,
        })
    }

    /// `BIT_addBits`: append the low `nb_bits` of `value` (nb_bits ≤ 31 by
    /// contract; the huff0/FSE call patterns keep `bit_pos + nb_bits < 64`).
    pub fn add_bits(&mut self, value: u64, nb_bits: u32) {
        debug_assert!(nb_bits < 64 && u64::from(nb_bits) + u64::from(self.bit_pos) < 64);
        let mask = if nb_bits >= 64 {
            u64::MAX
        } else {
            (1u64 << nb_bits) - 1
        };
        self.container |= (value & mask) << self.bit_pos;
        self.bit_pos += nb_bits;
    }

    /// `BIT_addBitsFast`: value must be clean (no bits above nb_bits).
    pub fn add_bits_fast(&mut self, value: u64, nb_bits: u32) {
        debug_assert!(value >> nb_bits == 0);
        debug_assert!(u64::from(nb_bits) + u64::from(self.bit_pos) < 64);
        self.container |= value << self.bit_pos;
        self.bit_pos += nb_bits;
    }

    /// `BIT_flushBits`: write the container LE, advance by whole bytes.
    pub fn flush_bits(&mut self) {
        let nb_bytes = (self.bit_pos >> 3) as usize;
        self.buf[self.pos..self.pos + 8].copy_from_slice(&self.container.to_le_bytes());
        self.pos += nb_bytes;
        if self.pos > self.end {
            self.pos = self.end;
            self.overflowed = true;
        }
        self.bit_pos &= 7;
        self.container >>= nb_bytes * 8;
    }

    /// `BIT_flushBitsFast` (no overflow clamp — callers guarantee headroom).
    pub fn flush_bits_fast(&mut self) {
        let nb_bytes = (self.bit_pos >> 3) as usize;
        self.buf[self.pos..self.pos + 8].copy_from_slice(&self.container.to_le_bytes());
        self.pos += nb_bytes;
        self.bit_pos &= 7;
        self.container >>= nb_bytes * 8;
    }

    /// `BIT_closeCStream`: sentinel 1 bit, final flush, and the size (or
    /// `None` on overflow — the C return code 0 meaning "did not fit").
    pub fn close(mut self) -> Option<Vec<u8>> {
        self.add_bits_fast(1, 1); // endMark
        self.flush_bits();
        if self.overflowed || self.pos >= self.end {
            return None;
        }
        let size = self.pos + usize::from(self.bit_pos > 0);
        self.buf.truncate(size);
        Some(self.buf)
    }

    /// Scratch-recycling close: APPENDS the finished stream to `out` and
    /// returns the (still allocated) backing buffer for reuse. `None` on
    /// overflow, exactly like [`close`].
    pub fn close_append(mut self, out: &mut Vec<u8>) -> Option<Vec<u8>> {
        self.add_bits_fast(1, 1); // endMark
        self.flush_bits();
        if self.overflowed || self.pos >= self.end {
            return None;
        }
        let size = self.pos + usize::from(self.bit_pos > 0);
        out.extend_from_slice(&self.buf[..size]);
        Some(self.buf)
    }
}

// ---------------------------------------------------------------------------
// Reader (BIT_DStream_t)
// ---------------------------------------------------------------------------

/// Reload status of [`BitReader`] (`BIT_DStream_status`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamStatus {
    /// Register holds ≥ 57 bits — safe to consume up to 4×12-bit symbols.
    Unfinished = 0,
    /// Fewer bits available; consume with care.
    EndOfBuffer = 1,
    /// Exactly all bits consumed.
    Completed = 2,
    /// Read past the start — corruption.
    Overflow = 3,
}

/// Backward bit reader mirroring `BIT_DStream_t` (bounds-checked).
pub struct BitReader<'a> {
    src: &'a [u8],
    container: u64,
    bits_consumed: u32,
    /// C `ptr - start`.
    ptr: usize,
    /// C `limitPtr - start` = 8 (container size).
    limit: usize,
}

impl<'a> BitReader<'a> {
    /// `BIT_initDStream`.
    ///
    /// # Errors
    /// Empty source, or a last byte of zero (missing sentinel `1` bit).
    pub fn init(src: &'a [u8]) -> CodecResult<Self> {
        if src.is_empty() {
            return Err(CodecError::Corrupt("empty bitstream".to_owned()));
        }
        let last = src[src.len() - 1];
        if last == 0 {
            return Err(CodecError::Corrupt(
                "bitstream endMark not present".to_owned(),
            ));
        }
        let pad_bits = 8 - highbit32(u32::from(last));
        if src.len() >= 8 {
            let ptr = src.len() - 8;
            Ok(Self {
                src,
                container: u64::from_le_bytes(src[ptr..].try_into().expect("8 bytes")),
                bits_consumed: pad_bits,
                ptr,
                limit: 8,
            })
        } else {
            // C builds the container byte-by-byte from the top: equivalent to
            // a zero-padded LE read plus (8-len)*8 pre-consumed bits.
            let mut bytes = [0u8; 8];
            bytes[..src.len()].copy_from_slice(src);
            let container = u64::from_le_bytes(bytes);
            Ok(Self {
                src,
                container,
                bits_consumed: pad_bits + (8 - src.len()) as u32 * 8,
                ptr: 0,
                limit: 8,
            })
        }
    }

    /// `BIT_lookBits` (peek n bits without consuming).
    #[inline]
    pub fn look_bits(&self, nb_bits: u32) -> u64 {
        // C BIT_getMiddleBits: (container >> (64 - consumed - nb)) & mask
        let shift = 64u32.wrapping_sub(self.bits_consumed).wrapping_sub(nb_bits) & 63;
        let mask = if nb_bits >= 64 {
            u64::MAX
        } else {
            (1u64 << nb_bits) - 1
        };
        (self.container >> shift) & mask
    }

    /// `BIT_lookBitsFast` (requires nb_bits ≥ 1).
    #[inline]
    pub fn look_bits_fast(&self, nb_bits: u32) -> u64 {
        debug_assert!(nb_bits >= 1);
        (self.container << (self.bits_consumed & 63)) >> ((64u32.wrapping_sub(nb_bits)) & 63)
    }

    #[inline]
    pub fn skip_bits(&mut self, nb_bits: u32) {
        self.bits_consumed += nb_bits;
    }

    /// `BIT_readBits`.
    #[inline]
    pub fn read_bits(&mut self, nb_bits: u32) -> u64 {
        let v = self.look_bits(nb_bits);
        self.skip_bits(nb_bits);
        v
    }

    /// `BIT_readBitsFast` (requires nb_bits ≥ 1).
    #[inline]
    pub fn read_bits_fast(&mut self, nb_bits: u32) -> u64 {
        let v = self.look_bits_fast(nb_bits);
        self.skip_bits(nb_bits);
        v
    }

    /// `BIT_reloadDStreamFast`.
    #[inline]
    pub fn reload_fast(&mut self) -> StreamStatus {
        if self.ptr < self.limit {
            return StreamStatus::Overflow;
        }
        self.ptr -= (self.bits_consumed >> 3) as usize;
        self.bits_consumed &= 7;
        self.container = self.read_le64_at(self.ptr);
        StreamStatus::Unfinished
    }

    /// `BIT_reloadDStream` (the safe variant with all four states).
    pub fn reload(&mut self) -> StreamStatus {
        if self.bits_consumed > 64 {
            return StreamStatus::Overflow;
        }
        if self.ptr >= self.limit {
            return self.reload_fast();
        }
        if self.ptr == 0 {
            return if self.bits_consumed < 64 {
                StreamStatus::EndOfBuffer
            } else {
                StreamStatus::Completed
            };
        }
        // 0 < ptr < limit
        let mut nb_bytes = (self.bits_consumed >> 3) as usize;
        let mut result = StreamStatus::Unfinished;
        if self.ptr < nb_bytes {
            nb_bytes = self.ptr;
            result = StreamStatus::EndOfBuffer;
        }
        self.ptr -= nb_bytes;
        self.bits_consumed -= (nb_bytes * 8) as u32;
        self.container = self.read_le64_at(self.ptr);
        result
    }

    /// `BIT_endOfDStream`: exactly everything consumed.
    #[inline]
    #[must_use]
    pub fn end_of_stream(&self) -> bool {
        self.ptr == 0 && self.bits_consumed == 64
    }

    /// Current `bitsConsumed` (C field access used by
    /// `HUF_decodeLastSymbolX2`).
    #[inline]
    #[must_use]
    pub fn consumed(&self) -> u32 {
        self.bits_consumed
    }

    /// Clamp `bitsConsumed` (the C's "ugly hack" in
    /// `HUF_decodeLastSymbolX2`).
    #[inline]
    pub fn set_consumed(&mut self, v: u32) {
        self.bits_consumed = v;
    }

    /// Bounds-checked LE64 window read (zero-padded — the C reads are
    /// in-bounds by construction, this keeps fuzzed logic bugs panic-free).
    #[inline]
    fn read_le64_at(&self, at: usize) -> u64 {
        let mut bytes = [0u8; 8];
        let n = (self.src.len() - at).min(8);
        bytes[..n].copy_from_slice(&self.src[at..at + n]);
        u64::from_le_bytes(bytes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn highbit_matches_c() {
        assert_eq!(highbit32(1), 0);
        assert_eq!(highbit32(2), 1);
        assert_eq!(highbit32(0xFF), 7);
        assert_eq!(highbit32(0x8000_0000), 31);
    }

    /// Write a known bit pattern, then verify the reader returns it exactly
    /// (LIFO order: first added is read first).
    #[test]
    fn writer_reader_roundtrip() {
        let mut w = BitWriter::new(64).expect("cap");
        let values: Vec<(u64, u32)> = vec![
            (0b101, 3),
            (0xABCD, 16),
            (1, 1),
            (0x3F, 6),
            (0xDEAD_BEEF, 32),
            (7, 5),
            (0xFF, 8),
            (3, 2),
        ];
        for &(v, n) in &values {
            w.add_bits(v, n);
            if w.bit_pos > 56 {
                w.flush_bits();
            }
        }
        let bytes = w.close().expect("fits");
        let mut r = BitReader::init(&bytes).expect("init");
        // LIFO semantics (bitstream.h): "the first bit sequence you add will
        // be the last to be read" — the backward reader returns items in
        // REVERSE order of addition.
        for &(v, n) in values.iter().rev() {
            // consume like the decoders do: reload, then read
            let _ = r.reload();
            assert_eq!(r.read_bits(n), v, "value {v} ({n} bits)");
        }
        // everything consumed: reload settles the window at ptr==0/consumed==64
        let _ = r.reload();
        assert!(
            r.end_of_stream(),
            "ptr/consumed: {}/{}",
            r.ptr,
            r.bits_consumed
        );
    }

    #[test]
    fn single_bit_stream() {
        // sentinel only: one byte 0b0000_0001 — init finds the sentinel at
        // bit 0, so all 64 window bits are "consumed" → end of stream.
        let w = BitWriter::new(16).expect("cap");
        let bytes = w.close().expect("fits");
        assert_eq!(bytes, vec![1]);
        let mut r = BitReader::init(&bytes).expect("init");
        assert!(r.end_of_stream());
        assert_eq!(r.reload(), StreamStatus::Completed);
    }

    #[test]
    fn reader_rejects_missing_sentinel() {
        assert!(BitReader::init(&[]).is_err());
        assert!(BitReader::init(&[0x00]).is_err());
        assert!(BitReader::init(&[0x10, 0x00]).is_err());
    }

    #[test]
    fn small_streams_use_the_padded_path() {
        // 3-byte stream: container is zero-padded, bits pre-consumed
        let mut r = BitReader::init(&[0xFF, 0xFF, 0b0010_0000]).expect("init");
        // last byte highbit = 5 → pad = 8-5 = 3; plus (8-3)*8 = 40 → 43
        assert_eq!(r.bits_consumed, 43);
        assert_eq!(r.ptr, 0);
        assert_eq!(r.reload(), StreamStatus::EndOfBuffer);
    }

    #[test]
    fn overflow_state_on_overconsumption() {
        let mut w = BitWriter::new(32).expect("cap");
        w.add_bits(0b11, 2);
        let bytes = w.close().expect("fits");
        let mut r = BitReader::init(&bytes).expect("init");
        r.skip_bits(64);
        r.skip_bits(8);
        assert_eq!(r.reload(), StreamStatus::Overflow);
    }

    #[test]
    fn writer_overflow_reports_none() {
        // capacity 16 → end = 8: force more than 8 bytes of output
        let mut w = BitWriter::new(16).expect("cap");
        for _ in 0..20 {
            w.add_bits(0xFF, 8);
            w.flush_bits();
        }
        assert!(w.close().is_none());
    }

    /// Cross-check against the exact byte layout the C writer produces for a
    /// known sequence (verified by hand from BIT_flushBits LE semantics):
    /// add 0b1011 (4 bits), add 0b110 (3), close → container 0b110_1011 =
    /// 0x6B, sentinel → 0b1_0110_1011... laid out LSB-first: bits [0..4) =
    /// 1011, [4..7) = 110, bit7 = 1 → single byte 0b1_110_1011 = 0xEB.
    #[test]
    fn byte_layout_is_lsb_first() {
        let mut w = BitWriter::new(16).expect("cap");
        w.add_bits(0b1011, 4);
        w.add_bits(0b110, 3);
        let bytes = w.close().expect("fits");
        assert_eq!(bytes, vec![0b1110_1011]);
    }
}
