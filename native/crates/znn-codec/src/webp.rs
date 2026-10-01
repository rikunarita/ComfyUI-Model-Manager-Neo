//! Phase 7 (Plan §3.8 追記 / T7) — the preview **WebP** codec.
//!
//! A thin, adversarial-input-hardened wrapper over [`zenwebp`] (the pure-Rust
//! VP8/VP8L codec). The preview pipeline in `py/utils.py` decodes an incoming
//! image (PIL for PNG/JPEG/GIF/BMP, this module for WebP) into an RGBA buffer
//! and re-encodes it as WebP; animated sources keep their frames through
//! [`encode_animation`]. Everything here is pure Rust (`znn-codec` denies
//! `unsafe_code`; zenwebp is `forbid(unsafe_code)` + upstream-fuzzed), so the
//! only soundness surface is *resource exhaustion* — every entry point guards
//! the canvas dimensions and the pixel count BEFORE allocating, and every
//! zenwebp error is mapped to [`WebpError`] (never a panic).
//!
//! [`decode_still`] is the L3 fuzz target (`webp_decode`): hostile WebP bytes
//! must always come back as `Err`, never a panic and never an allocation beyond
//! the input's own scale.
//!
//! Licence: zenwebp is **AGPL-3.0-only OR LicenseRef-Imazen-Commercial**. This
//! extension is GPL-3.0-only, so it is used under the AGPL-3.0 terms (AGPLv3
//! §13 explicitly permits combining with GPLv3 works) — see `native/NOTICE`,
//! the READMEs' Credits and Plan §8.

use zenwebp::{EncodeRequest, EncoderConfig, ImageInfo, PixelLayout, decoder::LoopCount};

/// zenwebp's own canvas ceiling (both [`decode_still`] and [`encode_still`]
/// reject anything larger; a hostile header claiming a gigantic canvas is
/// refused here BEFORE any `w * h * 4` allocation).
const MAX_DIMENSION: u32 = 16384;

/// Pixel-count ceiling. Previews are model thumbnails (rarely above ~4k×4k);
/// 64 Mpx (a 8192×8192 canvas = 256 MB of RGBA) is generous for a preview and
/// bounds a hostile decode to well inside the fuzz `rss_limit`.
const MAX_PIXELS: u64 = 64 * 1024 * 1024;

/// RGBA bytes per pixel (the only layout this module crosses the boundary in).
const BPP: usize = 4;

/// Encoder knobs. The defaults mirror PIL's `Image.save(..., "WEBP")` closely
/// enough that the pre/post-T7 preview sizes land in the same band (the pytest
/// parity gate is "same dimensions, decodable, size within a tolerance", not
/// byte-identity — the encoders differ).
#[derive(Debug, Clone, Copy)]
pub struct WebpEncodeOpts {
    /// Lossy quality (0.0..=100.0) / lossless effort hint.
    pub quality: f32,
    /// Compression method (0 = fast ..= 6 = slowest/smallest).
    pub method: u8,
    /// Lossless (VP8L) instead of lossy (VP8).
    pub lossless: bool,
}

impl Default for WebpEncodeOpts {
    fn default() -> Self {
        Self {
            quality: 80.0,
            method: 4,
            lossless: false,
        }
    }
}

/// Every failure mode of the preview WebP codec (mapped to a Python
/// `RuntimeError` by `mm-core`; the caller falls back to the PIL path).
#[derive(thiserror::Error, Debug)]
pub enum WebpError {
    /// zenwebp could not decode the input (corrupt / truncated / unsupported).
    #[error("webp decode failed: {0}")]
    Decode(String),
    /// zenwebp could not encode the pixels.
    #[error("webp encode failed: {0}")]
    Encode(String),
    /// The canvas is empty or beyond the dimension / pixel ceilings.
    #[error("webp canvas out of range: {0}")]
    Canvas(String),
    /// An RGBA buffer's length is not exactly `w * h * 4`.
    #[error("webp buffer length {got} != {w}x{h}x4 = {expected}")]
    BufferMismatch {
        got: usize,
        expected: usize,
        w: u32,
        h: u32,
    },
    /// No frames were supplied to the animation encoder.
    #[error("webp animation needs at least one frame")]
    NoFrames,
}

/// Reject an empty / oversized canvas before any pixel allocation.
fn guard_canvas(w: u32, h: u32) -> Result<(), WebpError> {
    if w == 0 || h == 0 || w > MAX_DIMENSION || h > MAX_DIMENSION {
        return Err(WebpError::Canvas(format!(
            "{w}x{h} outside 1..={MAX_DIMENSION}"
        )));
    }
    let pixels = u64::from(w) * u64::from(h);
    if pixels > MAX_PIXELS {
        return Err(WebpError::Canvas(format!(
            "{w}x{h} = {pixels} px > {MAX_PIXELS}"
        )));
    }
    Ok(())
}

/// The exact RGBA byte count of a `w × h` canvas (checked — an overflow here
/// would be a hostile-input bug, not a wrap).
fn rgba_len(w: u32, h: u32) -> Result<usize, WebpError> {
    (w as usize)
        .checked_mul(h as usize)
        .and_then(|n| n.checked_mul(BPP))
        .ok_or_else(|| WebpError::Canvas(format!("{w}x{h} overflows usize")))
}

/// Decode the first frame of a WebP into RGBA.
///
/// Returns `(rgba, width, height, icc_profile)` — `icc_profile` is empty when
/// the file carries no ICCP chunk. This is the still-image leg of the preview
/// pipeline (a WebP input is decoded here, re-encoded by [`encode_still`]) and
/// the **L3 fuzz surface**: `data` is treated as fully hostile, so the canvas
/// is validated from the header ([`ImageInfo::from_webp`]) BEFORE any decode
/// allocation, and every zenwebp error becomes [`WebpError::Decode`].
///
/// # Errors
/// [`WebpError::Decode`] on a corrupt / truncated / unsupported bitstream,
/// [`WebpError::Canvas`] on an empty or over-ceiling image,
/// [`WebpError::BufferMismatch`] if zenwebp ever returned a short buffer.
pub fn decode_still(data: &[u8]) -> Result<(Vec<u8>, u32, u32, Vec<u8>), WebpError> {
    // Header probe first: cheap, and it carries the dimensions we guard on plus
    // the ICC profile (decode_rgba does not surface ICC).
    let info = ImageInfo::from_webp(data).map_err(|e| WebpError::Decode(e.to_string()))?;
    guard_canvas(info.width, info.height)?;

    let (rgba, w, h) =
        zenwebp::oneshot::decode_rgba(data).map_err(|e| WebpError::Decode(e.to_string()))?;
    guard_canvas(w, h)?;
    let expected = rgba_len(w, h)?;
    if rgba.len() != expected {
        return Err(WebpError::BufferMismatch {
            got: rgba.len(),
            expected,
            w,
            h,
        });
    }
    Ok((rgba, w, h, info.icc_profile.unwrap_or_default()))
}

/// Every frame of a decoded animated WebP ([`decode_animation`]'s return).
#[derive(Debug, Clone)]
pub struct DecodedAnimation {
    /// Per-frame RGBA canvases (each `width * height * 4` bytes, zenwebp
    /// composites the sub-frames onto the full canvas).
    pub frames: Vec<Vec<u8>>,
    /// Canvas width.
    pub width: u32,
    /// Canvas height.
    pub height: u32,
    /// Per-frame display duration in milliseconds.
    pub durations_ms: Vec<u32>,
    /// Loop count (0 = forever).
    pub loop_count: u16,
    /// ICC profile (empty when the file carries no ICCP chunk).
    pub icc: Vec<u8>,
}

/// Decode every frame of an animated WebP.
///
/// Returns the frames + geometry + per-frame durations + loop count + ICC (a
/// [`DecodedAnimation`]). This is the WebP-input leg of the animation path: PIL
/// does NOT surface per-frame WebP durations, so an animated WebP preview is
/// decoded here (durations intact) and re-muxed by [`encode_animation`]. Canvas
/// dimensions are guarded from the header before any frame allocation.
///
/// # Errors
/// [`WebpError::Decode`] on a corrupt / non-animated bitstream,
/// [`WebpError::Canvas`] on an over-ceiling canvas, [`WebpError::NoFrames`] on
/// an empty animation, [`WebpError::BufferMismatch`] on a short frame.
pub fn decode_animation(data: &[u8]) -> Result<DecodedAnimation, WebpError> {
    use zenwebp::mux::AnimationDecoder;

    let info = ImageInfo::from_webp(data).map_err(|e| WebpError::Decode(e.to_string()))?;
    guard_canvas(info.width, info.height)?;

    let mut decoder = AnimationDecoder::new(data).map_err(|e| WebpError::Decode(e.to_string()))?;
    let anim = decoder.info();
    let (width, height) = (anim.canvas_width, anim.canvas_height);
    guard_canvas(width, height)?;
    let icc = decoder
        .icc_profile()
        .map_err(|e| WebpError::Decode(e.to_string()))?
        .unwrap_or_default();
    let decoded = decoder
        .decode_all()
        .map_err(|e| WebpError::Decode(e.to_string()))?;
    if decoded.is_empty() {
        return Err(WebpError::NoFrames);
    }
    // zenwebp composites each frame to RGBA (4 B/px) when the animation has
    // alpha and to RGB (3 B/px) when it does not (AnimationDecoder::
    // current_frame_data). Detect the layout from the frame length and
    // normalise to RGBA so `encode_animation` (Rgba8) always gets 4 B/px.
    let pixels = (width as usize)
        .checked_mul(height as usize)
        .ok_or_else(|| WebpError::Canvas(format!("{width}x{height} overflows usize")))?;
    let rgba_expected = pixels
        .checked_mul(BPP)
        .ok_or_else(|| WebpError::Canvas("rgba length overflows usize".to_string()))?;
    let rgb_expected = pixels
        .checked_mul(3)
        .ok_or_else(|| WebpError::Canvas("rgb length overflows usize".to_string()))?;
    let mut frames = Vec::with_capacity(decoded.len());
    let mut durations_ms = Vec::with_capacity(decoded.len());
    for frame in decoded {
        let rgba = match frame.data.len() {
            n if n == rgba_expected => frame.data,
            n if n == rgb_expected => rgb_to_rgba(&frame.data),
            n => {
                return Err(WebpError::BufferMismatch {
                    got: n,
                    expected: rgba_expected,
                    w: width,
                    h: height,
                });
            }
        };
        frames.push(rgba);
        durations_ms.push(frame.duration_ms);
    }
    let loop_count = match anim.loop_count {
        LoopCount::Forever => 0,
        LoopCount::Times(n) => n.get(),
    };
    Ok(DecodedAnimation {
        frames,
        width,
        height,
        durations_ms,
        loop_count,
        icc,
    })
}

/// Expand a packed RGB (3 B/px) buffer to RGBA (4 B/px, opaque alpha).
fn rgb_to_rgba(rgb: &[u8]) -> Vec<u8> {
    let mut rgba = Vec::with_capacity(rgb.len() / 3 * BPP);
    for px in rgb.chunks_exact(3) {
        rgba.extend_from_slice(&[px[0], px[1], px[2], 255]);
    }
    rgba
}

/// Encode an RGBA buffer (`w * h * 4` bytes) into a WebP bitstream.
///
/// The still-image leg of the preview pipeline: PIL (non-WebP input) or
/// [`decode_still`] (WebP input) hands over the pixels, this writes the WebP.
/// A non-empty `icc` is embedded as an ICCP chunk (colour management is NOT
/// applied — pixels pass through in their stored colour space, matching
/// libwebp/PIL).
///
/// # Errors
/// [`WebpError::Canvas`] / [`WebpError::BufferMismatch`] on a bad geometry,
/// [`WebpError::Encode`] if zenwebp rejects the pixels.
pub fn encode_still(
    rgba: &[u8],
    w: u32,
    h: u32,
    icc: &[u8],
    opts: &WebpEncodeOpts,
) -> Result<Vec<u8>, WebpError> {
    guard_canvas(w, h)?;
    let expected = rgba_len(w, h)?;
    if rgba.len() != expected {
        return Err(WebpError::BufferMismatch {
            got: rgba.len(),
            expected,
            w,
            h,
        });
    }
    let config = encoder_config(opts);
    let mut request = EncodeRequest::new(&config, rgba, PixelLayout::Rgba8, w, h);
    if !icc.is_empty() {
        request = request.with_icc_profile(icc);
    }
    request
        .encode()
        .map_err(|e| WebpError::Encode(e.to_string()))
}

/// Encode RGBA frames (each exactly `w * h * 4` bytes) into an **animated**
/// WebP, preserving the per-frame `durations_ms` and the `loop_count`
/// (0 = loop forever, matching PIL's `image.info["loop"]`).
///
/// This is what keeps an animated GIF / animated WebP preview animated instead
/// of freezing it to the first frame (the pre-T7 PIL behaviour). Frames are
/// presented by cumulative timestamp; zenwebp derives each frame's duration
/// from the gap to the next (and `finalize` sets the last one).
///
/// # Errors
/// [`WebpError::NoFrames`] on an empty frame list, [`WebpError::Canvas`] /
/// [`WebpError::BufferMismatch`] on a bad geometry, [`WebpError::Encode`] if
/// zenwebp rejects a frame or the assembly.
pub fn encode_animation(
    frames: &[Vec<u8>],
    w: u32,
    h: u32,
    durations_ms: &[u32],
    loop_count: u16,
    icc: &[u8],
    opts: &WebpEncodeOpts,
) -> Result<Vec<u8>, WebpError> {
    if frames.is_empty() {
        return Err(WebpError::NoFrames);
    }
    guard_canvas(w, h)?;
    let expected = rgba_len(w, h)?;
    for frame in frames {
        if frame.len() != expected {
            return Err(WebpError::BufferMismatch {
                got: frame.len(),
                expected,
                w,
                h,
            });
        }
    }

    let config = zenwebp::mux::AnimationConfig {
        loop_count: LoopCount::from(loop_count),
        ..zenwebp::mux::AnimationConfig::default()
    };
    let mut encoder = zenwebp::mux::AnimationEncoder::new(w, h, config)
        .map_err(|e| WebpError::Encode(e.to_string()))?;
    if !icc.is_empty() {
        encoder.icc_profile(icc.to_vec());
    }
    let enc_config = encoder_config(opts);

    let mut timestamp_ms: u32 = 0;
    for (index, frame) in frames.iter().enumerate() {
        encoder
            .add_frame(frame, PixelLayout::Rgba8, timestamp_ms, &enc_config)
            .map_err(|e| WebpError::Encode(e.to_string()))?;
        // Presentation time of the NEXT frame = this frame's duration away.
        let duration = durations_ms.get(index).copied().unwrap_or(100).max(1);
        timestamp_ms = timestamp_ms.saturating_add(duration);
    }
    let last_duration = durations_ms
        .get(frames.len() - 1)
        .copied()
        .unwrap_or(100)
        .max(1);
    encoder
        .finalize(last_duration)
        .map_err(|e| WebpError::Encode(e.to_string()))
}

/// Build the runtime-selectable encoder config from our options.
fn encoder_config(opts: &WebpEncodeOpts) -> EncoderConfig {
    let base = if opts.lossless {
        EncoderConfig::new_lossless()
    } else {
        EncoderConfig::new_lossy()
    };
    base.with_quality(opts.quality.clamp(0.0, 100.0))
        .with_method(opts.method.min(6))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn solid(w: u32, h: u32, [r, g, b, a]: [u8; 4]) -> Vec<u8> {
        let mut v = Vec::with_capacity((w * h * 4) as usize);
        for _ in 0..w * h {
            v.extend_from_slice(&[r, g, b, a]);
        }
        v
    }

    #[test]
    fn still_round_trips_and_is_decodable() {
        let opts = WebpEncodeOpts::default();
        let rgba = solid(24, 16, [200, 30, 30, 255]);
        let webp = encode_still(&rgba, 24, 16, &[], &opts).expect("encode");
        // The RIFF/WEBP container magic.
        assert_eq!(&webp[..4], b"RIFF");
        assert_eq!(&webp[8..12], b"WEBP");
        let (back, w, h, icc) = decode_still(&webp).expect("decode");
        assert_eq!((w, h), (24, 16));
        assert_eq!(back.len(), (24 * 16 * 4) as usize);
        assert!(icc.is_empty());
        // Lossy: not byte-identical, but the dominant colour survives.
        let (r, g, b) = (back[0], back[1], back[2]);
        assert!(r > 150 && g < 90 && b < 90, "decoded pixel {r},{g},{b}");
    }

    #[test]
    fn lossless_round_trips_byte_exact() {
        let opts = WebpEncodeOpts {
            lossless: true,
            ..WebpEncodeOpts::default()
        };
        let rgba = solid(8, 8, [1, 2, 3, 255]);
        let webp = encode_still(&rgba, 8, 8, &[], &opts).expect("encode");
        let (back, w, h, _) = decode_still(&webp).expect("decode");
        assert_eq!((w, h), (8, 8));
        assert_eq!(back, rgba, "lossless must be byte-exact");
    }

    #[test]
    fn icc_profile_survives_the_round_trip() {
        let opts = WebpEncodeOpts::default();
        let rgba = solid(8, 8, [10, 20, 30, 255]);
        let icc = b"fake-icc-profile-bytes".to_vec();
        let webp = encode_still(&rgba, 8, 8, &icc, &opts).expect("encode");
        let (_, _, _, back_icc) = decode_still(&webp).expect("decode");
        assert_eq!(back_icc, icc);
    }

    #[test]
    fn encode_rejects_a_mismatched_buffer() {
        let opts = WebpEncodeOpts::default();
        let err = encode_still(&[0u8; 10], 4, 4, &[], &opts).unwrap_err();
        assert!(matches!(err, WebpError::BufferMismatch { .. }), "{err}");
    }

    #[test]
    fn canvas_guards_reject_empty_and_oversized() {
        let opts = WebpEncodeOpts::default();
        assert!(matches!(
            encode_still(&[], 0, 4, &[], &opts).unwrap_err(),
            WebpError::Canvas(_)
        ));
        // 16384 x 16384 = 268 Mpx > MAX_PIXELS, refused before any allocation.
        assert!(matches!(
            encode_still(&[], 16384, 16384, &[], &opts).unwrap_err(),
            WebpError::Canvas(_)
        ));
    }

    #[test]
    fn decode_rejects_garbage_without_panicking() {
        for bad in [
            &b""[..],
            &b"RIFF\x00\x00\x00\x00WEBP"[..],
            &b"not a webp at all"[..],
            &b"RIFF\xff\xff\xff\xffWEBPVP8 "[..],
        ] {
            let _ = decode_still(bad); // must return Err, never panic
        }
        assert!(decode_still(b"garbage").is_err());
    }

    #[test]
    fn animation_round_trips_frame_count_and_durations() {
        let opts = WebpEncodeOpts::default();
        let frames = vec![
            solid(12, 10, [255, 0, 0, 255]),
            solid(12, 10, [0, 255, 0, 255]),
            solid(12, 10, [0, 0, 255, 255]),
        ];
        let durations = vec![120u32, 80, 200];
        let webp =
            encode_animation(&frames, 12, 10, &durations, 0, &[], &opts).expect("encode anim");
        assert_eq!(&webp[..4], b"RIFF");

        // Decode it back with zenwebp's animation decoder and check the shape.
        let info = ImageInfo::from_webp(&webp).expect("info");
        assert!(info.has_animation, "output must be an animated WebP");
        assert_eq!(info.frame_count, 3);
        assert_eq!((info.width, info.height), (12, 10));

        let mut decoder = zenwebp::mux::AnimationDecoder::new(&webp).expect("anim decoder");
        let decoded = decoder.decode_all().expect("decode_all");
        assert_eq!(decoded.len(), 3);
        let got: Vec<u32> = decoded.iter().map(|f| f.duration_ms).collect();
        assert_eq!(got, durations, "per-frame durations must be preserved");
    }

    #[test]
    fn animation_rejects_ragged_frames() {
        let opts = WebpEncodeOpts::default();
        let frames = vec![solid(8, 8, [0, 0, 0, 255]), vec![0u8; 10]];
        let err = encode_animation(&frames, 8, 8, &[100, 100], 0, &[], &opts).unwrap_err();
        assert!(matches!(err, WebpError::BufferMismatch { .. }), "{err}");
        assert!(matches!(
            encode_animation(&[], 8, 8, &[], 0, &[], &opts).unwrap_err(),
            WebpError::NoFrames
        ));
    }

    #[test]
    fn decode_animation_returns_frames_durations_and_loop() {
        let opts = WebpEncodeOpts::default();
        let frames = vec![
            solid(10, 8, [255, 0, 0, 255]),
            solid(10, 8, [0, 255, 0, 255]),
        ];
        let durations = vec![50u32, 250];
        let webp = encode_animation(&frames, 10, 8, &durations, 7, &[], &opts).expect("encode");
        let anim = decode_animation(&webp).expect("decode_animation");
        assert_eq!((anim.width, anim.height), (10, 8));
        assert_eq!(anim.frames.len(), 2, "both frames come back");
        assert_eq!(anim.frames[0].len(), (10 * 8 * 4) as usize);
        assert_eq!(
            anim.durations_ms, durations,
            "durations preserved through the round trip"
        );
        assert_eq!(anim.loop_count, 7);
        assert!(anim.icc.is_empty());
    }

    #[test]
    fn animation_icc_profile_survives_the_round_trip() {
        // The Python pipeline reads `icc` from decode_animation and hands it
        // back to encode_animation (py/utils.py::_encode_preview_webp_native);
        // this pins the Rust half of that junction - an animation carrying an
        // ICCP chunk must come back with the same profile bytes.
        let opts = WebpEncodeOpts::default();
        let frames = vec![solid(6, 5, [9, 8, 7, 255]), solid(6, 5, [1, 2, 3, 255])];
        let icc = b"animation-icc-profile-bytes".to_vec();
        let webp = encode_animation(&frames, 6, 5, &[40, 60], 2, &icc, &opts).expect("encode anim");
        let anim = decode_animation(&webp).expect("decode_animation");
        assert_eq!(anim.icc, icc, "ICCP survives the animation round trip");
        assert_eq!(anim.loop_count, 2);
        assert_eq!(anim.durations_ms, vec![40, 60]);
    }

    #[test]
    fn decode_animation_rejects_a_still_webp() {
        // A still (non-animated) WebP is not an animation: decode_animation
        // must come back empty-handed rather than panic.
        let opts = WebpEncodeOpts::default();
        let webp = encode_still(&solid(6, 6, [1, 2, 3, 255]), 6, 6, &[], &opts).expect("encode");
        assert!(decode_animation(&webp).is_err());
    }
}
