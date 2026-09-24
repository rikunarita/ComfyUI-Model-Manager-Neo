//! ZN header codec — the 32-byte container header + the packed-shape
//! extension (Plan Appendix B.1).
//!
//! Byte-for-byte semantics mirror `third_party/zipnn/zipnn.py`
//! (`_update_header` / `_retrieve_header`) and `util_torch.py`
//! (`zipnn_pack_shape` / `zipnn_unpack_shape`), re-read on 2026-09-23:
//!
//! ```text
//! [0:2]   magic "ZN"
//! [2:5]   version major/minor/tiny (0.5.4)
//! [5]     byte_reorder  (220 = 4 planes, 10 = 2 planes / 1 plane, ...)
//! [6]     bit_reorder   (1 = sign/exponent reorder active)
//! [7]     method        (1 = HUFFMAN; anything else is an explicit error)
//! [8]     input_format  (1 = BYTE, 2 = TORCH, 3 = NUMPY)
//! [9]     delta_compressed_type (0 = none, 1 = byte, 2 = file)
//! [10:13] lossy triple  (always 0 in lossless files; non-zero = error)
//! [13]    streaming: MSB set = streaming; low 7 bits = log2(streaming_chunk)
//! [14]    log2(compression_chunk)  (default 18 = 256 KiB)
//! [15]    dtype code    (Plan §4.6.3 / dtype.rs)
//! [16:24] original_len  (u64 LE)
//! [24:32] comp_len field: the BYTE single-group path writes comp_len+32
//!         (`_update_header_comp_len`); the `zipnn_core` path overwrites it
//!         with the total payload size `resBufSize` (C `py_zipnn_core`:
//!         `memcpy(header.buf + 24, &resBufSize, 8)`). Decompression never
//!         reads it — keep the field, do not trust it.
//! [32..]  packed shape (TORCH/NUMPY only): ndims u8, then per dim a width
//!         indicator (1/2/4/8) + the value LE.
//! ```
//!
//! The decompressor validates everything it consumes (Plan §4.4.2): magic,
//! method, lossy-zero, and (Phase 1 scope) rejects delta/streaming payloads
//! with explicit errors — they land in Phase 3.

// `dim as u8/u16/u32` casts in `pack_shape` are range-checked immediately
// before the cast (the width indicator IS the range check).
#![allow(clippy::cast_possible_truncation)]

use crate::{CodecError, CodecResult, HEADER_LEN, ZNN_MAGIC};

/// Input format tag of header byte 8.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputFormat {
    Byte = 1,
    Torch = 2,
    Numpy = 3,
}

impl InputFormat {
    fn from_u8(v: u8) -> CodecResult<Self> {
        match v {
            1 => Ok(Self::Byte),
            2 => Ok(Self::Torch),
            3 => Ok(Self::Numpy),
            other => Err(CodecError::Header(format!("unknown input_format {other}"))),
        }
    }

    /// True when a packed shape follows the 32-byte header.
    pub fn has_shape(self) -> bool {
        matches!(self, Self::Torch | Self::Numpy)
    }
}

/// The parsed 32-byte ZN header.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ZnHeader {
    pub version: [u8; 3],
    pub byte_reorder: u8,
    pub bit_reorder: u8,
    pub method: u8,
    pub input_format: InputFormat,
    pub delta_compressed_type: u8,
    pub lossy: [u8; 3],
    pub streaming: bool,
    pub streaming_chunk_log2: u8,
    pub compression_chunk_log2: u8,
    pub dtype_code: u8,
    pub original_len: u64,
    /// Bytes 24–32: written by the encoders (see module docs), never read
    /// back on decode. Kept so re-encoding a parsed header is lossless.
    pub comp_len_field: u64,
}

/// Compression method tag of header byte 7 (only HUFFMAN exists).
pub const METHOD_HUFFMAN: u8 = 1;

impl ZnHeader {
    /// Parse the fixed 32-byte header. Strict about everything a decoder
    /// must not guess (magic, method, lossy-zero); `input_format` validity
    /// included. Does NOT parse the packed shape (see [`parse`]).
    pub fn decode(buf: &[u8]) -> CodecResult<Self> {
        if buf.len() < HEADER_LEN {
            return Err(CodecError::Header(format!(
                "need {HEADER_LEN} bytes, got {}",
                buf.len()
            )));
        }
        if buf[0..2] != ZNN_MAGIC {
            return Err(CodecError::Header("missing ZN magic".to_owned()));
        }
        // Strict version gate (Plan §7 R10): Neo implements the ZipNN 0.5.4
        // wire format; a NEWER upstream version could change semantics, and
        // silently mis-decoding it is the exact failure mode R10 guards
        // against — refuse with an actionable message instead. (Older minors
        // than 0.5 predate every .znn file in the ecosystems Neo reads —
        // the HF ZipNN collections and the official CLI are all 0.5.x.)
        let version = [buf[2], buf[3], buf[4]];
        if version[0] != 0 || version[1] != 5 || version[2] > 4 {
            return Err(CodecError::Header(format!(
                "unsupported ZipNN container version {}.{}.{} (Neo implements the 0.5.4 format)",
                version[0], version[1], version[2]
            )));
        }
        let method = buf[7];
        if method != METHOD_HUFFMAN {
            return Err(CodecError::Unsupported(format!(
                "compression method {method} (only HUFFMAN=1 is supported; Plan Appendix B.1)"
            )));
        }
        let lossy = [buf[10], buf[11], buf[12]];
        if lossy != [0, 0, 0] {
            return Err(CodecError::Unsupported(format!(
                "lossy compression flags {lossy:?} are non-zero (lossless files carry 0/0/0)"
            )));
        }
        Ok(Self {
            version: [buf[2], buf[3], buf[4]],
            byte_reorder: buf[5],
            bit_reorder: buf[6],
            method,
            input_format: InputFormat::from_u8(buf[8])?,
            delta_compressed_type: buf[9],
            lossy,
            streaming: buf[13] & 0x80 != 0,
            // The low 7 bits are the streaming_chunk log2 ONLY when the
            // streaming flag is set (zipnn.py writes a plain 0 otherwise and
            // its reader ignores the low bits — normalising here keeps
            // encode∘decode canonical, which the L3 zn_header fuzz target
            // asserts as an invariant; found by the fuzzer within seconds).
            streaming_chunk_log2: if buf[13] & 0x80 != 0 {
                buf[13] & 0x7F
            } else {
                0
            },
            compression_chunk_log2: buf[14],
            dtype_code: buf[15],
            original_len: u64::from_le_bytes(buf[16..24].try_into().expect("8 bytes")),
            comp_len_field: u64::from_le_bytes(buf[24..32].try_into().expect("8 bytes")),
        })
    }

    /// Serialize back to exactly 32 bytes (round-trips [`decode`]).
    #[must_use]
    pub fn encode(&self) -> [u8; HEADER_LEN] {
        let mut out = [0u8; HEADER_LEN];
        out[0..2].copy_from_slice(&ZNN_MAGIC);
        out[2] = self.version[0];
        out[3] = self.version[1];
        out[4] = self.version[2];
        out[5] = self.byte_reorder;
        out[6] = self.bit_reorder;
        out[7] = self.method;
        out[8] = self.input_format as u8;
        out[9] = self.delta_compressed_type;
        out[10] = self.lossy[0];
        out[11] = self.lossy[1];
        out[12] = self.lossy[2];
        out[13] = if self.streaming {
            0x80 | self.streaming_chunk_log2
        } else {
            0
        };
        out[14] = self.compression_chunk_log2;
        out[15] = self.dtype_code;
        out[16..24].copy_from_slice(&self.original_len.to_le_bytes());
        out[24..32].copy_from_slice(&self.comp_len_field.to_le_bytes());
        out
    }

    /// Decode + the Phase-1 scope guards for PAYLOAD consumption: delta and
    /// streaming containers are Phase 3 work — refuse them explicitly
    /// (never mis-decode). `chunk_size` = the compression chunk the payload
    /// was built with (2^compression_chunk_log2), sanity-checked > 0.
    pub fn validate_for_decode(&self) -> CodecResult<usize> {
        if self.delta_compressed_type != 0 {
            return Err(CodecError::Unsupported(format!(
                "delta_compressed_type={} payloads are handled by the delta codec (Plan Phase 3)",
                self.delta_compressed_type
            )));
        }
        if self.streaming {
            return Err(CodecError::Unsupported(
                "streaming payloads are handled by the delta codec (Plan Phase 3)".to_owned(),
            ));
        }
        if self.compression_chunk_log2 == 0 || self.compression_chunk_log2 > 63 {
            return Err(CodecError::Header(format!(
                "compression_chunk log2 {} outside 1..=63",
                self.compression_chunk_log2
            )));
        }
        Ok(1usize << self.compression_chunk_log2)
    }

    /// Parse a full container prefix: 32-byte header + (for TORCH/NUMPY) the
    /// packed shape. Returns the header, the shape (empty for BYTE) and the
    /// total prefix length.
    pub fn parse(buf: &[u8]) -> CodecResult<(Self, Vec<u64>, usize)> {
        let header = Self::decode(buf)?;
        if !header.input_format.has_shape() {
            return Ok((header, Vec::new(), HEADER_LEN));
        }
        let (shape, used) = unpack_shape(&buf[HEADER_LEN..])?;
        Ok((header, shape, HEADER_LEN + used))
    }
}

/// `zipnn_pack_shape` (util_torch.py): ndims byte, then per dimension a
/// width indicator (1/2/4/8) + the value little-endian.
#[must_use]
pub fn pack_shape(shape: &[u64]) -> Vec<u8> {
    let mut out = Vec::with_capacity(1 + shape.len() * 5);
    // The C/Python writers put the dim count in one byte; shapes longer than
    // 255 dims cannot be represented (torch caps far below) — clamp is never
    // hit in practice, but stay in-range instead of truncating silently.
    out.push(u8::try_from(shape.len()).unwrap_or(u8::MAX));
    for &dim in shape {
        if dim < 256 {
            out.push(1);
            out.push(dim as u8);
        } else if dim < 65536 {
            out.push(2);
            out.extend_from_slice(&(dim as u16).to_le_bytes());
        } else if dim < 4_294_967_296 {
            out.push(4);
            out.extend_from_slice(&(dim as u32).to_le_bytes());
        } else {
            out.push(8);
            out.extend_from_slice(&dim.to_le_bytes());
        }
    }
    out
}

/// `zipnn_unpack_shape` (util_torch.py): returns the dimensions and the
/// number of bytes consumed. Hostile input (bad width indicator, truncated
/// tail) is an error, never a panic.
pub fn unpack_shape(packed: &[u8]) -> CodecResult<(Vec<u64>, usize)> {
    let err = || CodecError::Shape("truncated packed shape".to_owned());
    let Some((&ndims, rest)) = packed.split_first() else {
        return Err(err());
    };
    let mut dims = Vec::with_capacity(ndims as usize);
    let mut pos = 0usize;
    for _ in 0..ndims {
        let indicator = *rest.get(pos).ok_or_else(err)?;
        pos += 1;
        let width = match indicator {
            1 | 2 | 4 | 8 => indicator as usize,
            other => {
                return Err(CodecError::Shape(format!(
                    "bad dim width indicator {other} (must be 1/2/4/8)"
                )));
            }
        };
        let bytes = rest.get(pos..pos + width).ok_or_else(err)?;
        let dim = match width {
            1 => u64::from(bytes[0]),
            2 => u16::from_le_bytes(bytes.try_into().expect("2 bytes")) as u64,
            4 => u32::from_le_bytes(bytes.try_into().expect("4 bytes")) as u64,
            _ => u64::from_le_bytes(bytes.try_into().expect("8 bytes")),
        };
        dims.push(dim);
        pos += width;
    }
    Ok((dims, pos + 1))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> ZnHeader {
        ZnHeader {
            version: [0, 5, 4],
            byte_reorder: 220,
            bit_reorder: 1,
            method: METHOD_HUFFMAN,
            input_format: InputFormat::Torch,
            delta_compressed_type: 0,
            lossy: [0, 0, 0],
            streaming: false,
            streaming_chunk_log2: 0,
            compression_chunk_log2: 18,
            dtype_code: 1,
            original_len: 123_456_789,
            comp_len_field: 0,
        }
    }

    #[test]
    fn header_roundtrip_is_byte_exact() {
        let h = sample();
        let bytes = h.encode();
        assert_eq!(bytes.len(), HEADER_LEN);
        let back = ZnHeader::decode(&bytes).expect("decode");
        assert_eq!(back, h);
    }

    #[test]
    fn header_matches_the_python_layout() {
        // Bytes pinned against zipnn.py `_update_header` semantics and a real
        // production header dump (fp8: [90,78,0,5,4,10,1,1,2,0,...,18,29]).
        let h = ZnHeader {
            byte_reorder: 10,
            dtype_code: 29,
            input_format: InputFormat::Torch,
            ..sample()
        };
        let b = h.encode();
        assert_eq!(&b[0..10], &[90, 78, 0, 5, 4, 10, 1, 1, 2, 0]);
        assert_eq!(b[13], 0);
        assert_eq!(b[14], 18);
        assert_eq!(b[15], 29);
        assert_eq!(
            u64::from_le_bytes(b[16..24].try_into().unwrap()),
            123_456_789
        );
    }

    #[test]
    fn decode_rejects_hostile_headers() {
        let mut b = sample().encode();
        b[0] = b'X';
        assert!(ZnHeader::decode(&b).is_err(), "magic");
        let mut b = sample().encode();
        b[7] = 2;
        assert!(ZnHeader::decode(&b).is_err(), "method");
        let mut b = sample().encode();
        b[11] = 3;
        assert!(ZnHeader::decode(&b).is_err(), "lossy");
        let mut b = sample().encode();
        b[8] = 9;
        assert!(ZnHeader::decode(&b).is_err(), "input_format");
        assert!(ZnHeader::decode(&b[..10]).is_err(), "short");
    }

    /// Plan §7 R10: the version bytes are gated strictly — anything outside
    /// 0.5.0..=0.5.4 is an explicit error, never a silent mis-decode.
    #[test]
    fn decode_gates_the_container_version() {
        for tiny in 0u8..=4 {
            let h = ZnHeader {
                version: [0, 5, tiny],
                ..sample()
            };
            assert!(ZnHeader::decode(&h.encode()).is_ok(), "0.5.{tiny}");
        }
        for version in [
            [0u8, 5, 5],
            [0, 5, 255],
            [0, 6, 0],
            [1, 0, 0],
            [0, 0, 0],
            [0, 4, 9],
        ] {
            let h = ZnHeader {
                version,
                ..sample()
            };
            let err = ZnHeader::decode(&h.encode()).unwrap_err().to_string();
            assert!(err.contains("version"), "{err}");
        }
    }

    #[test]
    fn streaming_bit_layout() {
        let h = ZnHeader {
            streaming: true,
            streaming_chunk_log2: 20,
            ..sample()
        };
        assert_eq!(h.encode()[13], 128 + 20);
        let back = ZnHeader::decode(&h.encode()).expect("decode");
        assert!(back.streaming && back.streaming_chunk_log2 == 20);
        // streaming containers are Phase 3 scope — validate must refuse them
        assert!(back.validate_for_decode().is_err());
    }

    #[test]
    fn validate_refuses_delta_and_bad_chunk_log() {
        let h = ZnHeader {
            delta_compressed_type: 1,
            ..sample()
        };
        assert!(h.validate_for_decode().is_err());
        let h = ZnHeader {
            compression_chunk_log2: 0,
            ..sample()
        };
        assert!(h.validate_for_decode().is_err());
        assert_eq!(sample().validate_for_decode().expect("valid"), 262_144);
    }

    #[test]
    fn shape_pack_unpack_roundtrip() {
        for shape in [
            vec![],
            vec![7],
            vec![255],
            vec![256],
            vec![65535],
            vec![65536],
            vec![1, 2, 3, 28672, 4096],
            vec![u64::from(u32::MAX), 1 << 33, u64::MAX],
        ] {
            let packed = pack_shape(&shape);
            let (dims, used) = unpack_shape(&packed).expect("unpack");
            assert_eq!(dims, shape);
            assert_eq!(used, packed.len());
            // width indicators follow the documented thresholds
            assert_eq!(packed[0] as usize, shape.len());
        }
    }

    #[test]
    fn shape_unpack_rejects_hostile_input() {
        assert!(unpack_shape(&[]).is_err()); // no ndims byte
        assert!(unpack_shape(&[2, 1, 5]).is_err()); // truncated dim
        assert!(unpack_shape(&[1, 3, 0]).is_err()); // bad width indicator
        assert!(unpack_shape(&[1, 4, 1, 2]).is_err()); // truncated 4-byte dim
    }

    #[test]
    fn parse_torch_prefix_consumes_the_shape() {
        let h = sample(); // input_format = Torch
        let mut blob = h.encode().to_vec();
        let shape = vec![4096u64, 4096];
        blob.extend_from_slice(&pack_shape(&shape));
        blob.extend_from_slice(&[0xAA; 64]); // payload stub
        let (hp, sp, used) = ZnHeader::parse(&blob).expect("parse");
        assert_eq!(hp, h);
        assert_eq!(sp, shape);
        assert_eq!(used, HEADER_LEN + 1 + 3 + 3);
        let hb = ZnHeader {
            input_format: InputFormat::Byte,
            ..h
        };
        let blob = hb.encode();
        let (_, sp, used) = ZnHeader::parse(&blob).expect("parse");
        assert!(sp.is_empty() && used == HEADER_LEN);
    }
}
