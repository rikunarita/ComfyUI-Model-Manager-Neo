//! Integration tests of the Neo extension band (Phase 4) — PUBLIC API only.
//!
//! Per the crate's test organisation (Plan §3.4.3, native/README): unit tests
//! live inline next to the code they exercise (`#[cfg(test)]`, private access);
//! this `tests/` folder manages the crate-level END-TO-END gates that must
//! hold through the public surface alone — the same API the `mm_core`
//! PyO3 layer and `znn-cli` consume. Keeping them here proves the extension
//! band is a property of the crate's contract, not of its internals.
//!
//! Covers (Plan §6.2 Phase 4 完了条件 "全拡張 dtype 往復 green (K14)"):
//! * every safetensors 0.8 dtype (all 22 spellings) round-trips byte-exactly
//!   through `compress_tensor`/`decompress_tensor` with the truncation
//!   auto-selection a production caller applies;
//! * the dtype-code table matches Plan §4.6.3 exactly (codes, bands, and the
//!   compatibility set that official ZipNN tools can decode);
//! * codec-level-only pseudo dtypes (complex128/bcomplex32 — no safetensors
//!   representation) round-trip at the blob level and report their pseudo
//!   names (the safetensors pipeline refuses to RESTORE them — pinned by the
//!   pipeline unit tests);
//! * the band-strict mode gate: compatibility blobs refuse truncation modes,
//!   Neo integer blobs accept exactly their own.

use znn_codec::dtype::{self, Band};
use znn_codec::znn_tensor::{
    compress_tensor, decompress_tensor, scheme_for_st_dtype, select_truncation, st_dtype_for_code,
};

/// Deterministic LCG bytes (the same family the inline fixtures use).
fn lcg_bytes(n: usize, seed: u32) -> Vec<u8> {
    let mut x = seed | 1;
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        x = x.wrapping_mul(1664525).wrapping_add(1013904223);
        out.push((x >> 16) as u8);
    }
    out
}

/// Low-entropy float-ish payloads compress; random mantissas mostly store
/// raw. For the round-trip GATE the entropy does not matter — correctness
/// must hold for both — so each dtype gets a deterministic mix.
fn payload(st: &str, bytes: usize, seed: u32) -> Vec<u8> {
    match st {
        // f64 words with concentrated sign/exponent (weight-like)
        "F64" => {
            let mut out = Vec::with_capacity(bytes);
            let mut x = seed | 1;
            while out.len() + 8 <= bytes {
                x = x.wrapping_mul(1664525).wrapping_add(1013904223);
                let v = ((x >> 8) as f64 / 8_388_608.0 - 1.0) * 0.01;
                out.extend_from_slice(&v.to_le_bytes());
            }
            out
        }
        // small positive i32s → truncatable (byte 2/3 zero)
        "I32" | "U32" => {
            let mut out = Vec::with_capacity(bytes);
            let mut x = seed | 1;
            while out.len() + 4 <= bytes {
                x = x.wrapping_mul(1664525).wrapping_add(1013904223);
                out.extend_from_slice(&(x % 60_000).to_le_bytes());
            }
            out
        }
        // small i64s → zero top planes (8-plane huff0 collapse)
        "I64" | "U64" => {
            let mut out = Vec::with_capacity(bytes);
            let mut x = seed | 1;
            while out.len() + 8 <= bytes {
                x = x.wrapping_mul(1664525).wrapping_add(1013904223);
                out.extend_from_slice(&u64::from(x % 100_000).to_le_bytes());
            }
            out
        }
        // {0,1} masks
        "BOOL" => (0..bytes).map(|i| u8::from(i % 4 == 0)).collect(),
        _ => lcg_bytes(bytes, seed),
    }
}

/// (safetensors dtype, code, band is Neo, element BYTES for the payload grid;
/// sub-byte types use their packed byte count and a shape in ELEMENTS)
const CASES: &[(&str, u8, bool)] = &[
    ("F32", 1, false),
    ("F16", 4, false),
    ("BF16", 6, false),
    ("F8_E4M3", 29, false),
    ("F8_E5M2", 30, false),
    ("F64", 128, true),
    ("C64", 130, true),
    ("I8", 132, true),
    ("U8", 133, true),
    ("BOOL", 134, true),
    ("I16", 135, true),
    ("U16", 136, true),
    ("I32", 137, true),
    ("U32", 138, true),
    ("I64", 139, true),
    ("U64", 140, true),
    ("F8_E4M3FNUZ", 141, true),
    ("F8_E5M2FNUZ", 142, true),
    ("F8_E8M0", 143, true),
    ("F4", 144, true),
    ("F6_E2M3", 145, true),
    ("F6_E3M2", 146, true),
];

#[test]
fn every_safetensors_dtype_roundtrips_byte_exact() {
    for &(st, code, neo) in CASES {
        let base = scheme_for_st_dtype(st).unwrap_or_else(|| panic!("scheme for {st}"));
        assert_eq!(base.dtype_code, code, "{st} code (Plan §4.6.3)");
        assert_eq!(base.is_neo(), neo, "{st} band");
        assert_eq!(
            dtype::scheme_for_dtype(code).unwrap().band,
            if neo { Band::Neo } else { Band::Compat },
            "{st} band via dtype.rs"
        );

        // payload sized to a whole number of elements (bits-based for F4/F6)
        let bits = base.bits_per_elem;
        let nelem = 9_000u64; // × bits always lands on a byte boundary below
        let nbytes = (nelem * bits as u64 / 8) as usize;
        let data = payload(st, nbytes, 7 + code as u32);
        assert_eq!(data.len(), nbytes, "{st} payload grid");

        // the production caller's flow: truncation auto-selection, then blob
        let scheme = select_truncation(&base, &data);
        let blob = compress_tensor(&scheme, &data, &[nelem], 0, None).expect("compress");
        assert_eq!(blob[15], code, "{st} blob dtype code");
        // truncation may only ever pick a mode the dtype's table allows
        assert!(
            base.allows_mode(blob[5]),
            "{st}: blob mode {} outside the dtype's table",
            blob[5]
        );
        if st == "I32" || st == "U32" {
            assert_eq!(blob[5], 9, "{st} small values must truncate to 2 bytes");
        }

        let back = decompress_tensor(&blob, 0, None).expect("decompress");
        assert_eq!(back.data, data, "{st} byte-exact round trip");
        assert_eq!(back.st_dtype, st);
        assert_eq!(back.shape, vec![nelem]);
        // the recorded torch name survives the code round trip
        let (st2, torch2) = st_dtype_for_code(code).unwrap();
        assert_eq!((st2, torch2), (back.st_dtype, back.torch_name));
    }
}

#[test]
fn codec_only_pseudo_dtypes_roundtrip_at_blob_level() {
    // complex128 (129) and bcomplex32 (131): real torch dtypes WITHOUT a
    // safetensors 0.8 representation — the blob layer must still serve them
    // (the pipeline refuses to RESTORE them into a safetensors header).
    for (st, code, word_bytes, elem_bytes) in
        [("C128", 129u8, 8usize, 16usize), ("BC32", 131, 2, 4)]
    {
        let scheme = scheme_for_st_dtype(st).expect("pseudo scheme");
        assert_eq!(scheme.dtype_code, code);
        assert_eq!(scheme.num_planes, word_bytes);
        assert_eq!(scheme.bits_per_elem, elem_bytes * 8);
        let nelem = 2_000u64;
        let data = payload("F64", (nelem * elem_bytes as u64) as usize, 99);
        let blob = compress_tensor(&scheme, &data, &[nelem], 0, None).expect("compress");
        assert_eq!(blob[15], code);
        let back = decompress_tensor(&blob, 0, None).expect("decompress");
        assert_eq!(back.data, data, "{st} byte-exact");
        assert_eq!(back.st_dtype, st);
        // and the pseudo names are NOT valid safetensors dtypes (the reason
        // the pipeline refuses them — dtype_bitsize is the authority)
        assert!(
            znn_codec::safetensors_io::dtype_bitsize(st).is_none(),
            "{st} must have no safetensors representation"
        );
    }
}

#[test]
fn mode_gate_is_band_strict_through_the_public_api() {
    // a compatibility blob patched to a truncation mode must be REFUSED
    // (official encoders never write those modes — reinterpretation would be
    // guesswork); the same mode on its Neo integer dtype is legal.
    let bf16 = scheme_for_st_dtype("BF16").unwrap();
    let data = payload("BF16", 64 * 1024, 21);
    let mut blob = compress_tensor(&bf16, &data, &[32 * 1024], 0, None).unwrap();
    assert_eq!(blob[5], 10);
    blob[5] = 1; // fake a truncation mode onto a compat blob
    let err = decompress_tensor(&blob, 0, None)
        .expect_err("compat blob with a truncation mode must be refused");
    assert!(
        err.to_string().contains("not valid for dtype code"),
        "{err}"
    );

    let i16 = scheme_for_st_dtype("I16").unwrap();
    let data16: Vec<u8> = (0..20_000u32)
        .flat_map(|i| ((i % 200) as u16).to_le_bytes())
        .collect();
    let scheme = select_truncation(&i16, &data16);
    assert_eq!(
        scheme.byte_reorder, 1,
        "small i16 → truncate to the low byte"
    );
    let blob = compress_tensor(&scheme, &data16, &[20_000], 0, None).unwrap();
    assert_eq!(blob[5], 1);
    let back = decompress_tensor(&blob, 0, None).expect("legal truncation decodes");
    assert_eq!(back.data, data16);

    // mode 8 (keep the HIGH byte) on multiples of 256
    let data_hi: Vec<u8> = (0..20_000u32)
        .flat_map(|i| (((i % 200) * 256) as u16).to_le_bytes())
        .collect();
    let scheme = select_truncation(&i16, &data_hi);
    assert_eq!(scheme.byte_reorder, 8);
    let blob = compress_tensor(&scheme, &data_hi, &[20_000], 0, None).unwrap();
    let back = decompress_tensor(&blob, 0, None).expect("mode 8 decodes");
    assert_eq!(back.data, data_hi);
}

#[test]
fn compatibility_set_is_exactly_the_five_official_dtypes() {
    // The interop contract (README matrix / L5): exactly these five
    // safetensors dtypes produce official-decodable files.
    let compat: Vec<&str> = CASES
        .iter()
        .filter(|&&(_, _, neo)| !neo)
        .map(|&(st, _, _)| st)
        .collect();
    assert_eq!(compat, ["F32", "F16", "BF16", "F8_E4M3", "F8_E5M2"]);
    // every other table entry is Neo band, and every code 128..=146 is
    // assigned exactly once (no gaps, no duplicates)
    let mut neo_codes: Vec<u8> = CASES.iter().filter(|c| c.2).map(|c| c.1).collect();
    neo_codes.extend([129u8, 131]); // the two codec-only pseudo dtypes
    neo_codes.sort_unstable();
    assert_eq!(neo_codes, (128..=146).collect::<Vec<u8>>());
    // alias codes keep decoding like their primaries
    assert_eq!(st_dtype_for_code(2).unwrap(), st_dtype_for_code(1).unwrap());
    assert_eq!(st_dtype_for_code(5).unwrap(), st_dtype_for_code(4).unwrap());
}
