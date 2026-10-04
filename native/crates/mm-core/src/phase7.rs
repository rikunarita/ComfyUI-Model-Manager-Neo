//! Phase 7 bindings — the preview **WebP** codec (T7).
//!
//! Thin PyO3 wrappers over [`znn_codec::webp`] (the zenwebp-backed pure-Rust
//! codec). Boundary rules: pixels cross as `bytes` (previews are
//! small — a model thumbnail, never a multi-GB payload), every codec call runs
//! with the GIL released (the input buffer is copied to an owned `Vec` first so
//! the borrow never outlives the detach), and every [`WebpError`] becomes a
//! `RuntimeError` — the Python caller (`py/utils.py`) catches it and falls back
//! to the PIL path, so a native failure degrades, never breaks a preview save.
//!
//! Licence: zenwebp is AGPL-3.0-only (see `native/NOTICE`).

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use znn_codec::webp::{self, WebpEncodeOpts};

fn opts(quality: f32, method: u8, lossless: bool) -> WebpEncodeOpts {
    WebpEncodeOpts {
        quality,
        method,
        lossless,
    }
}

/// Decode the first frame of a WebP into RGBA.
///
/// Returns `(rgba, width, height, icc_profile)`; `icc_profile` is empty when the
/// file carries no ICCP chunk. The WebP-decode leg of the preview pipeline (a
/// WebP input is decoded here, re-encoded by [`webp_encode`]) and the surface
/// the L3 `webp_decode` fuzz target drives. Hostile input comes back as a
/// `RuntimeError`, never a panic. GIL released for the decode.
pub fn webp_decode(py: Python<'_>, data: &[u8]) -> PyResult<(Vec<u8>, u32, u32, Vec<u8>)> {
    let data = data.to_vec();
    py.detach(move || webp::decode_still(&data).map_err(|e| PyRuntimeError::new_err(e.to_string())))
}

/// Encode an RGBA buffer (`w * h * 4` bytes) into WebP bytes.
///
/// The still-image leg of the preview pipeline: PIL (non-WebP input) or
/// [`webp_decode`] (WebP input) supplies the pixels; a non-empty `icc` is
/// embedded as an ICCP chunk. `quality` (0..=100), `method` (0..=6) and
/// `lossless` mirror PIL's `save(..., "WEBP")` knobs. GIL released.
#[allow(clippy::too_many_arguments)] // a flat PyO3 signature (Python passes the encoder knobs)
pub fn webp_encode(
    py: Python<'_>,
    rgba: &[u8],
    w: u32,
    h: u32,
    icc: &[u8],
    quality: f32,
    method: u8,
    lossless: bool,
) -> PyResult<Vec<u8>> {
    let rgba = rgba.to_vec();
    let icc = icc.to_vec();
    let o = opts(quality, method, lossless);
    py.detach(move || {
        webp::encode_still(&rgba, w, h, &icc, &o)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })
}

/// Decode every frame of an animated WebP: returns
/// `(frames_rgba, width, height, durations_ms, loop_count, icc)`. The WebP-input
/// leg of the animation path — PIL does not surface per-frame WebP durations, so
/// an animated WebP preview is decoded here (durations intact) and re-muxed by
/// [`webp_encode_animation`]. GIL released; a still / corrupt input raises.
#[allow(clippy::type_complexity)] // the flat Python tuple of the animation decode
pub fn webp_decode_animation(
    py: Python<'_>,
    data: &[u8],
) -> PyResult<(Vec<Vec<u8>>, u32, u32, Vec<u32>, u16, Vec<u8>)> {
    let data = data.to_vec();
    py.detach(move || {
        webp::decode_animation(&data)
            .map(|a| {
                (
                    a.frames,
                    a.width,
                    a.height,
                    a.durations_ms,
                    a.loop_count,
                    a.icc,
                )
            })
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })
}

/// Encode RGBA frames (each `w * h * 4` bytes) into an **animated** WebP.
///
/// `durations_ms` is the per-frame display time (a missing entry defaults to
/// 100 ms), `loop_count` is 0 = forever (matching PIL's `image.info["loop"]`).
/// This is what keeps an animated GIF / WebP preview animated instead of
/// freezing it to the first frame (the pre-T7 PIL behaviour). GIL released.
#[allow(clippy::too_many_arguments)] // a flat PyO3 signature (frames + durations + encoder knobs)
pub fn webp_encode_animation(
    py: Python<'_>,
    frames: Vec<Vec<u8>>,
    w: u32,
    h: u32,
    durations_ms: Vec<u32>,
    loop_count: u16,
    icc: &[u8],
    quality: f32,
    method: u8,
    lossless: bool,
) -> PyResult<Vec<u8>> {
    let icc = icc.to_vec();
    let o = opts(quality, method, lossless);
    py.detach(move || {
        webp::encode_animation(&frames, w, h, &durations_ms, loop_count, &icc, &o)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })
}
