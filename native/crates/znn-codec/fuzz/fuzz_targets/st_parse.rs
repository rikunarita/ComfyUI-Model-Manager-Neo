//! L3 fuzz target 4/5: the safetensors CONTAINER parser + the canonical
//! writer round trip (Phase 2's hostile-file surface — ComfyUI loads
//! third-party models, Plan §4.4.2). Exercises: the u64 prefix guards, the
//! jiter-driven header parse (duplicate keys, unknown fields, non-string
//! metadata, negative/huge integers), the reference validation rules
//! (dtype table, nbits%8, dense offsets, exact coverage), the per-entry
//! `data()` bounds, and the canonical rebuild. Every path must return Err —
//! never panic, never allocate beyond the input's own scale.
#![no_main]

use libfuzzer_sys::fuzz_target;
use znn_codec::safetensors_io::{build_header_region, OutEntry, StContainer};

fuzz_target!(|data: &[u8]| {
    let Ok(st) = StContainer::parse(data) else {
        return;
    };
    // parsed successfully: every entry slice must be bounds-checked…
    for t in &st.tensors {
        let _ = st.data(data, t);
    }
    // …and the canonical writer must serialise the parsed form without
    // panicking (round-trip re-parse when the input claimed canonicity)
    let entries: Vec<OutEntry> = st
        .tensors
        .iter()
        .map(|t| OutEntry {
            name: &t.name,
            dtype: &t.dtype,
            shape: &t.shape,
            start: t.start,
            end: t.end,
        })
        .collect();
    let rebuilt = build_header_region(st.metadata.as_deref(), &entries);
    if st.canonical {
        // the canonicity contract: rebuild == the original region bytes
        let region_len = st.header_region_len as usize;
        assert_eq!(
            &rebuilt[..],
            &data[8..8 + region_len],
            "canonical flag lied — rebuild differs"
        );
        // and a rebuild of a rebuild is stable (idempotence)
        let reparse = {
            let mut img = Vec::with_capacity(8 + rebuilt.len());
            img.extend_from_slice(&(rebuilt.len() as u64).to_le_bytes());
            img.extend_from_slice(&rebuilt);
            img.extend_from_slice(&data[8 + region_len..]);
            StContainer::parse(&img).expect("canonical rebuild must re-parse")
        };
        assert!(reparse.canonical, "rebuild of canonical is canonical");
    }
});
