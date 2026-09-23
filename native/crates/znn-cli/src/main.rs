//! `znn-cli` — validation CLI for the native core (Plan §4.2.1: "検証用 CLI
//! (配布しない)"). Phase 0 ships only the identity report; the inspection /
//! round-trip verification subcommands grow alongside the codec in Phase 1+
//! (`inspect <file.znn.safetensors>`, `verify <src> <dst>`, golden-file
//! helpers for the L2 differential tests).

fn main() {
    println!(
        "znn-cli {version} (znn-codec scaffold: magic {magic:?}, header {header} B, \
         huff0 block max {block} B, tableLog max {log_max} / default {log_default}, \
         default chunk {chunk} B)",
        version = env!("CARGO_PKG_VERSION"),
        magic = znn_codec::ZNN_MAGIC,
        header = znn_codec::HEADER_LEN,
        block = znn_codec::HUF_BLOCKSIZE_MAX,
        log_max = znn_codec::HUF_TABLELOG_MAX,
        log_default = znn_codec::HUF_TABLELOG_DEFAULT,
        chunk = znn_codec::DEFAULT_CHUNK,
    );
}
