//! L3 fuzz target 1/3: the huff0 block decoder against fully hostile input
//! (Plan §5.1 L3 / §4.4.2). The decoder is the trust boundary for existing
//! `.znn` archives: malformed weight headers, jump tables and bitstreams
//! must produce `Err`, never a panic / OOB / unbounded allocation.
//!
//! `dst_size` is derived from the input (capped at 64 KiB) so the fuzzer
//! explores the size-mismatch paths too; the C decoder's own guards
//! (dstSize==0, cSrcSize>dstSize, cSrcSize==dstSize memcpy, RLE) are part
//! of the surface.
#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    if data.len() < 3 {
        return;
    }
    let dst_size = (u16::from_le_bytes([data[0], data[1]]) as usize % (64 * 1024)) + 1;
    let _ = znn_codec::huf::decompress_block(&data[2..], dst_size);
    // also exercise the scratch-recycling entry point used by the codec
    let mut dst = Vec::new();
    let mut entries = znn_codec::huf::decode::new_dtable_scratch();
    let _ = znn_codec::huf::decompress_block_into(&data[2..], dst_size, &mut dst, &mut entries);
});
