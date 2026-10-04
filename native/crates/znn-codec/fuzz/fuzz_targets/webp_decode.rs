//! L3 fuzz target 7/7: hostile WebP bytes → the zenwebp DECODE path
//! (Phase 7 / T7). The preview pipeline decodes untrusted CDN images, and while
//! zenwebp is pure Rust (`forbid(unsafe_code)`, upstream-fuzzed), v0.4.x is
//! young — so T7 makes the decode path a permanent fuzz surface (an adoption
//! precondition, not a deferral).
//!
//! Every input must come back `Ok` (validated pixels) or `Err` — never a panic,
//! never an allocation beyond the canvas ceilings (`decode_still` /
//! `decode_animation` guard the dimensions from the header BEFORE allocating,
//! and cap the pixel count). On a successful decode the RGBA buffer is exactly
//! `w * h * 4` and, for a modestly sized image, a re-encode round-trips back to
//! the same geometry (the codec is self-consistent even on weird-but-valid
//! input).
#![no_main]

use libfuzzer_sys::fuzz_target;
use znn_codec::webp::{decode_animation, decode_still, encode_still, WebpEncodeOpts};

/// Re-encode only modest canvases so a highly-compressed-but-huge valid decode
/// cannot make one exec slow (the decode ceiling itself is the memory guard).
const REENCODE_MAX_PIXELS: u32 = 1_000_000;

fuzz_target!(|data: &[u8]| {
    // --- still decode path -------------------------------------------------
    if let Ok((rgba, w, h, _icc)) = decode_still(data) {
        assert_eq!(
            rgba.len(),
            (w as usize) * (h as usize) * 4,
            "decoded RGBA must be exactly w*h*4"
        );
        if w.saturating_mul(h) <= REENCODE_MAX_PIXELS {
            let opts = WebpEncodeOpts::default();
            if let Ok(webp) = encode_still(&rgba, w, h, &[], &opts) {
                let (rgba2, w2, h2, _) = decode_still(&webp).expect("a freshly encoded WebP must decode");
                assert_eq!((w2, h2), (w, h), "re-encode preserves geometry");
                assert_eq!(rgba2.len(), rgba.len());
            }
        }
    }

    // --- animation decode path (hostile input may claim to be animated) -----
    if let Ok(anim) = decode_animation(data) {
        let expected = (anim.width as usize) * (anim.height as usize) * 4;
        assert!(!anim.frames.is_empty(), "a decoded animation has >= 1 frame");
        assert_eq!(
            anim.durations_ms.len(),
            anim.frames.len(),
            "one duration per frame"
        );
        for frame in &anim.frames {
            assert_eq!(frame.len(), expected, "every frame is a full RGBA canvas");
        }
    }
});
