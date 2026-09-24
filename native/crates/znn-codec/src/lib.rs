//! `znn-codec` — pure-Rust `ZipNN` codec (Plan §3.6, §4.2.1).
//!
//! This crate is the Python-independent heart of the native core: the ZipNN
//! byte format (ZN header + plane split + huff0/FSE chunks), safetensors I/O,
//! the streaming delta codec, the parallel library scan and the multi-hash
//! pass. Phase 1 (Plan §6.2) implements the format core:
//!
//! | module             | contents                                                     |
//! |--------------------|--------------------------------------------------------------|
//! | [`header`]         | ZN header 32 B + packed shape (Plan Appendix B.1)            |
//! | [`dtype`]          | dtype <-> header code <-> plane scheme tables (Plan §4.6.3)  |
//! | [`reorder`]        | sign/exponent bit reorder (f32, bf16, f64 schemes) + reverts |
//! | [`planes`]         | N-plane split/join (N = 1, 2, 4), exact C in-bounds layout   |
//! | [`bitstream`]      | the FSE/huff0 backward bit reader / forward bit writer       |
//! | [`fse`]            | FSE normalized-count tables: decode (weights) + encode       |
//! | [`huf`]            | huff0 per RFC 8878 §4.2 (weights, 4X decode, encode)         |
//! | [`codec`]          | the `zipnn_core` equivalent layer (chunking, threshold,      |
//! |                    | chunkTypes/cumSizes layout — byte-identical structure to C)  |
//! | [`safetensors_io`] | mmap container parse, canonical order-preserving writer,     |
//! |                    | atomic `.tmp` → fsync → rename (Phase 2)                     |
//! | [`znn_tensor`]     | per-tensor ZN blobs + the compatibility-band dtype table     |
//! | [`pipeline`]       | the compress/decompress jobs: integrity pipeline, progress,  |
//! |                    | cancellation, paranoid mode (Phase 2)                        |
//!
//! Later phases add `delta`, `scan` and `hash` (Phase 3–5).
//!
//! Correctness strategy (Plan §5.1): L1 unit/proptest suites here, L2
//! differential tests against the bundled prebuilt C core (golden generator,
//! `scripts/l2/`), L3 cargo-fuzz on hostile inputs (`fuzz/`) — and the
//! Appendix C crash cases are permanent regression tests: every documented
//! C-core SEGFAULT input must answer with [`CodecError`] or a correct result,
//! never a crash or UB.
//!
//! Compatibility contract (Plan §4.5):
//! * the decoder accepts 100% of what the vendored C encoder (FiniteState
//!   `HUF_compress`) produces, and validates hostile input (header values,
//!   cumulative sizes, stream bounds, allocation caps) instead of trusting it;
//! * the encoder targets BYTE-IDENTICAL output to the C encoder (same
//!   tableLog choice, same tree build, same weight-encoding choice, same
//!   bitstream order) so L2 can golden-diff compressed bytes, not just ratios.
//!
//! Lint policy (Plan §3.4.2): workspace lints (pedantic = warn, unsafe =
//! deny); the format core (Phase 1) contains NO `unsafe` at all. Phase 2
//! adds exactly ONE reviewed unsafe boundary: the read-only `memmap2`
//! mapping in [`safetensors_io::StContainer::open`] (documented SAFETY
//! block; the zero-copy mmap design is Plan §3.7/§4.3 itself, and the
//! Python safetensors reader this replaces mmaps identically).

// Phase 1 kept the whole crate unsafe-free; the deny makes any further
// introduction a conscious, reviewed change (with `// SAFETY:` comments).
// The single reviewed exception (the mmap boundary) carries a function-level
// `#[allow(unsafe_code)]` next to its SAFETY block.
#![deny(unsafe_code)]

pub mod bitstream;
pub mod codec;
pub mod dtype;
pub mod fse;
pub mod header;
pub mod huf;
pub mod pipeline;
pub mod planes;
pub mod reorder;
pub mod safetensors_io;
pub mod znn_tensor;

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
pub const HUF_TABLELOG_MAX: u32 = 12;

/// Default huff0 `tableLog` (`HUF_TABLELOG_DEFAULT`, vendored `huf.h` L118) —
/// what `HUF_compress` (and therefore the vendored C core) encodes with.
pub const HUF_TABLELOG_DEFAULT: u32 = 11;

/// Default compression chunk as a log2: header byte 14 holds `18`, i.e.
/// 256 KiB (Plan Appendix B.1; `zipnn.py` `compression_chunk=256*1024`).
pub const DEFAULT_CHUNK_LOG2: u8 = 18;

/// Default compression chunk in bytes (`2^DEFAULT_CHUNK_LOG2`).
pub const DEFAULT_CHUNK: usize = 1 << DEFAULT_CHUNK_LOG2;

/// Compression decision threshold of the vendored core (`zipnn.py` default
/// `compression_threshold=0.95`; C: `comp < uncomp * threshold` in f64).
pub const DEFAULT_THRESHOLD: f64 = 0.95;

/// One codec-level error type (Plan §4.4.2: hostile input must produce
/// errors, never panics / UB / unbounded allocation).
#[derive(Debug, thiserror::Error)]
pub enum CodecError {
    #[error("invalid ZN header: {0}")]
    Header(String),
    #[error("invalid packed shape: {0}")]
    Shape(String),
    #[error("unsupported parameter: {0}")]
    Unsupported(String),
    #[error("corrupted payload: {0}")]
    Corrupt(String),
    #[error("huff0 block error: {0}")]
    Huff0(String),
    #[error("fse table error: {0}")]
    Fse(String),
    #[error("input/output size error: {0}")]
    Size(String),
    #[error("operation cancelled")]
    Cancelled,
}

/// Convenience alias used across the crate and by consumers.
pub type CodecResult<T> = Result<T, CodecError>;

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
