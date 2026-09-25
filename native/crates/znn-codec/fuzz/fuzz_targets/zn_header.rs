//! L3 fuzz target 2/3: the ZN header + packed-shape parser against hostile
//! bytes (Plan §5.1 L3). Parsing must be total: every input either yields a
//! validated header/shape or an error — never a panic, never an unbounded
//! allocation (ndims is a single byte; dim widths are 1/2/4/8-checked).
#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let _ = znn_codec::header::ZnHeader::decode(data);
    let _ = znn_codec::header::unpack_shape(data);
    if let Ok((header, shape, used)) = znn_codec::header::ZnHeader::parse(data) {
        assert!(used <= data.len());
        // re-encode round-trip: decode(encode(h)) == h, and the packed
        // shape must survive pack → unpack unchanged
        let bytes = header.encode();
        let back = znn_codec::header::ZnHeader::decode(&bytes).expect("re-decode");
        assert_eq!(back, header);
        let packed = znn_codec::header::pack_shape(&shape);
        if let Ok((dims, used2)) = znn_codec::header::unpack_shape(&packed) {
            assert_eq!(dims, shape);
            assert_eq!(used2, packed.len());
        }
        // validate_for_decode must stay consistent (chunk log2 in 1..=63)
        let _ = header.validate_for_decode();
    }
});
