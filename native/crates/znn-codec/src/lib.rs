//! `znn-codec` — pure-Rust ZipNN codec (Plan §3.6, §4.2.1).
//!
//! This crate is the Python-independent heart of the native core: the ZipNN
//! byte format (ZN header + plane split + huff0/FSE chunks), safetensors I/O,
//! the streaming delta codec, the parallel library scan and the multi-hash
//! pass. Phase 0 (Plan §6.2) lands only this scaffold; the format work is
//! Phase 1, planned module map:
//!
//! | module             | contents                                                    |
//! |--------------------|-------------------------------------------------------------|
//! | `header.rs`        | ZN header 32 B + packed shape (Plan Appendix B.1)            |
//! | `reorder.rs`       | sign/exponent bit reorder (f64/f32/bf16)                     |
//! | `planes.rs`        | N-plane split/join (N = 1, 2, 4, 8) + safe tail handling    |
//! | `huf/`             | huff0 per RFC 8878 §4.2 (compress / decompress / FSE tables) |
//! | `codec.rs`         | chunk-parallel layer equivalent to `zipnn_core.c`            |
//! | `safetensors_io.rs`| mmap read, key-order-preserving writer, atomic replace       |
//! | `dtype.rs`         | dtype <-> sign code <-> plane scheme tables (Plan §4.6)      |
//! | `delta.rs`         | streaming XOR delta (1 MB chunks)                            |
//! | `scan.rs`          | parallel walk + front-matter + persistent index              |
//! | `hash.rs`          | multi-algorithm single-pass hashing                          |
//!
//! Correctness strategy (Plan §5.1): L1 unit/proptest suites, L2 differential
//! tests against the bundled prebuilt C core (golden generator), L3 cargo-fuzz
//! on hostile inputs — and the Appendix C crash cases become permanent
//! regression tests ("error or correct behaviour, never a crash or UB").
//!
//! License notes (Plan §8): this crate is GPL-3.0-only like the repository;
//! the Phase 1 `huf/` port derives from FiniteStateEntropy, which is used
//! under its BSD-2-Clause option (dual-licensed BSD-2-Clause OR GPL-2.0) with
//! per-file attribution, and the format/semantics reference ZipNN (MIT,
//! attributed in `native/NOTICE`).

// Phase 0 needs no `unsafe` at all; keep it denied so any future introduction
// is a conscious, reviewed change (with `// SAFETY:` comments, Plan §3.4.2).
#![deny(unsafe_code)]

/// Magic bytes of the ZipNN container: the ZN header starts with `b"ZN"`
/// (Plan Appendix B.1, offsets 0–1; `zipnn.py` `_update_header`).
pub const ZNN_MAGIC: [u8; 2] = *b"ZN";

/// Fixed length of the ZN header in bytes. A variable-length packed shape
/// (dim count + per-dim values) follows it, but only for TORCH/NUMPY inputs
/// (Plan Appendix B.1; `zipnn.py` `header_length = 32`).
pub const HEADER_LEN: usize = 32;

/// Maximum input size of a single huff0 block
/// (`HUF_BLOCKSIZE_MAX`, vendored `huf.h` L72). The Python layer clamps the
/// compression chunk to this value for the single-plane FP8 path.
pub const HUF_BLOCKSIZE_MAX: usize = 128 * 1024;

/// Maximum huff0 `tableLog` (`HUF_TABLELOG_MAX`, vendored `huf.h` L117).
pub const HUF_TABLELOG_MAX: u8 = 12;

/// Default huff0 `tableLog` (`HUF_TABLELOG_DEFAULT`, vendored `huf.h` L118).
pub const HUF_TABLELOG_DEFAULT: u8 = 11;

/// Default compression chunk as a log2: header byte 14 holds `18`, i.e.
/// 256 KiB (Plan Appendix B.1; `zipnn.py` `compression_chunk=256*1024`).
pub const DEFAULT_CHUNK_LOG2: u8 = 18;

/// Default compression chunk in bytes (`2^DEFAULT_CHUNK_LOG2`).
pub const DEFAULT_CHUNK: usize = 1 << DEFAULT_CHUNK_LOG2;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn constants_match_the_vendored_c_core() {
        // Values verified against third_party/zipnn/zipnn.py and
        // third_party/zipnn-core/include/FiniteStateEntropy/lib/huf.h.
        assert_eq!(ZNN_MAGIC, *b"ZN");
        assert_eq!(HEADER_LEN, 32);
        assert_eq!(HUF_BLOCKSIZE_MAX, 131_072);
        assert_eq!(HUF_TABLELOG_MAX, 12);
        assert_eq!(HUF_TABLELOG_DEFAULT, 11);
        assert_eq!(DEFAULT_CHUNK, 262_144);
    }
}
