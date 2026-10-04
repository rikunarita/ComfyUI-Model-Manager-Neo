"""Phase 7 / T7 - the preview WebP pipeline goes native (zenwebp).

`py/utils.py::_write_preview_content` used to re-encode every preview with PIL
(`Image.open(...).save(..., "WEBP")`), which also FROZE an animated GIF / WebP
to its first frame. T7 routes the image leg through the native zenwebp core:
a WebP input is decoded by zenwebp, a non-WebP input by PIL, and the RGBA is
re-encoded by zenwebp - stills as still WebP, animated sources as ANIMATED
WebP (frames + durations preserved). The native core is the rollback unit: a
failure (or `MM_NATIVE=0`) falls back to the exact pre-T7 PIL path.

The parity gate is a BEHAVIOUR contract, not byte-identity (the encoders
differ): "same dimensions, decodable, size within a tolerance band". These
tests pin that, the animation preservation (frames, per-frame durations, the
loop count and the ICC profile at the container-byte level) and the native
WebP decode. Phase 8 retired the PIL re-encode fallback together with the
MM_NATIVE switch: the zenwebp pipeline is the SINGLE image path, so a missing
core or an undecodable input surfaces the historical RuntimeError instead of
silently re-encoding through PIL. Every test here skips cleanly where no
native artifact is built (ci.yml on dev); on main and in the native
workflow's integration job the committed/built binary runs them for real.
"""

from __future__ import annotations

import io
import os

import pytest
from harness import REPO_ROOT, import_ext

pytest.importorskip("PIL", reason="the preview pipeline needs pillow")


def _reset_native_loader():
    config = import_ext("config")
    config.extension_uri = str(REPO_ROOT)
    native = import_ext("native")
    native._module = None
    native._reason = None
    native._attempted = False
    return native


def _require_native():
    """Load the native core (skip when absent) — the only path since Phase 8."""
    native = _reset_native_loader()
    if native.core_if_enabled() is None:
        pytest.skip(f"native core unavailable: {native.reason()}")
    return native


def _gradient_png(width: int, height: int) -> bytes:
    """A non-trivial image (gradient + noise) so WebP sizes are representative
    (a solid colour compresses to almost nothing and hides size regressions)."""
    from PIL import Image

    img = Image.new("RGB", (width, height))
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = ((x * 7 + y * 3) % 256, (x * 3 + y * 11) % 256, (x * y) % 256)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _webp_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """The top-level RIFF chunks of a WebP as ``(fourcc, payload)`` pairs."""
    import struct

    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return []
    chunks: list[tuple[bytes, bytes]] = []
    i, n = 12, len(data)
    while i + 8 <= n:
        fourcc = data[i : i + 4]
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        payload = data[i + 8 : i + 8 + size]
        chunks.append((fourcc, payload))
        i += 8 + size + (size & 1)  # RIFF chunks are padded to an even size
    return chunks


def _webp_anmf_durations(data: bytes) -> list[int]:
    """Per-frame durations (ms) parsed from an animated WebP's ANMF chunks.

    PIL's WebP reader does not surface per-frame ``duration`` through
    ``info`` (it reports ``n_frames`` but leaves duration unset), so the
    preservation contract is checked at the byte level - the ANMF frame header
    carries Frame Duration as a 24-bit LE value at payload offset 12.
    """
    durations: list[int] = []
    for fourcc, payload in _webp_chunks(data):
        if fourcc == b"ANMF" and len(payload) >= 16:
            durations.append(int.from_bytes(payload[12:15], "little"))
    return durations


def _webp_anim_loop_count(data: bytes) -> int | None:
    """The ANIM chunk's Loop Count (u16 LE at payload offset 4, after the
    4-byte background colour); ``None`` when the file carries no ANIM chunk.

    Byte-level on purpose: neither PIL's ``info`` nor ``n_frames`` surfaces
    the loop count of a WebP, so the preservation contract (a GIF's Netscape
    loop / a source WebP's ANIM loop must survive the re-mux) is only pinned
    by parsing the container.
    """
    for fourcc, payload in _webp_chunks(data):
        if fourcc == b"ANIM" and len(payload) >= 6:
            return int.from_bytes(payload[4:6], "little")
    return None


def _webp_iccp(data: bytes) -> bytes | None:
    """The ICCP chunk payload (``None`` when the file carries no ICC profile)."""
    for fourcc, payload in _webp_chunks(data):
        if fourcc == b"ICCP":
            return payload
    return None


# ---------------------------------------------------------------------------
# still parity: native vs the PIL reference (same dims, decodable, size band)
# ---------------------------------------------------------------------------
def test_native_still_webp_parity_with_pil(tmp_path):
    """The native encode produces a WebP of the SAME dimensions as PIL's, that
    decodes, and whose size is in the same band (the T7 parity contract)."""
    _require_native()
    utils = import_ext("utils")
    from PIL import Image

    content = _gradient_png(96, 64)

    # native path (production _write_preview_content)
    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    utils._write_preview_content(str(model), content, "image/png", "src.png", "")
    native_webp = (tmp_path / "m.webp").read_bytes()

    # PIL reference (the pre-T7 behaviour)
    pil_buf = io.BytesIO()
    Image.open(io.BytesIO(content)).save(pil_buf, "WEBP")
    pil_webp = pil_buf.getvalue()

    assert native_webp[:4] == b"RIFF" and native_webp[8:12] == b"WEBP"
    with Image.open(io.BytesIO(native_webp)) as n_img, Image.open(io.BytesIO(pil_webp)) as p_img:
        assert n_img.format == "WEBP"
        assert n_img.size == p_img.size == (96, 64), "dimensions must match PIL"
        n_img.load()  # decodable
    ratio = len(native_webp) / max(1, len(pil_webp))
    assert 0.4 < ratio < 2.5, f"native/PIL size ratio {ratio:.2f} outside the tolerance band"


def test_native_webp_input_is_decoded_natively(tmp_path):
    """A WebP INPUT is decoded by zenwebp (not PIL) and re-encoded - the round
    trip keeps dimensions and stays decodable."""
    native = _require_native()
    utils = import_ext("utils")
    from PIL import Image

    # Build a WebP input.
    src = io.BytesIO()
    Image.open(io.BytesIO(_gradient_png(48, 36))).save(src, "WEBP")
    webp_in = src.getvalue()

    mm = native.core_if_enabled()
    rgba, w, h, _icc = mm.webp_decode(webp_in)
    assert (w, h) == (48, 36)
    assert len(rgba) == 48 * 36 * 4

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    utils._write_preview_content(str(model), webp_in, "image/webp", "src.webp", "")
    out = (tmp_path / "m.webp").read_bytes()
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "WEBP" and img.size == (48, 36)
        img.load()


# ---------------------------------------------------------------------------
# animation preservation (the real Civitai-preview regression T7 removes)
# ---------------------------------------------------------------------------
def test_animated_gif_becomes_an_animated_webp(tmp_path):
    """An animated GIF preview keeps its frame count and per-frame durations
    (the pre-T7 PIL path froze it to frame 0)."""
    _require_native()
    utils = import_ext("utils")
    from PIL import Image

    frames = [Image.new("RGB", (24, 18), c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]]
    gif = tmp_path / "anim.gif"
    frames[0].save(
        gif,
        save_all=True,
        append_images=frames[1:],
        duration=[100, 200, 300],
        loop=0,
    )
    content = gif.read_bytes()

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    utils._write_preview_content(str(model), content, "image/gif", "anim.gif", "")
    out = (tmp_path / "m.webp").read_bytes()

    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "WEBP"
        assert getattr(img, "n_frames", 1) == 3, "animation must survive (3 frames)"
    # durations are preserved in the ANMF chunks (PIL doesn't surface them)
    assert _webp_anmf_durations(out) == [100, 200, 300]


def test_animated_webp_input_stays_animated(tmp_path):
    """An animated WebP input is re-muxed to an animated WebP (not flattened)."""
    _require_native()
    utils = import_ext("utils")
    from PIL import Image

    frames = [Image.new("RGB", (20, 20), c) for c in [(10, 20, 30), (40, 50, 60)]]
    src = tmp_path / "anim.webp"
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=[150, 250], loop=0)
    content = src.read_bytes()

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    utils._write_preview_content(str(model), content, "image/webp", "anim.webp", "")
    out = (tmp_path / "m.webp").read_bytes()
    with Image.open(io.BytesIO(out)) as img:
        assert getattr(img, "n_frames", 1) == 2
    assert _webp_anmf_durations(out) == [150, 250], "animated WebP durations preserved"


def test_animation_loop_count_is_preserved(tmp_path):
    """The source loop count survives the re-mux (ANIM chunk, byte level).

    Both animation legs must carry it: an animated GIF's Netscape loop
    (``image.info["loop"]``, read AFTER the frame iteration - PIL keeps the
    key) and an animated WebP's ANIM loop (from ``webp_decode_animation``).
    A regression that hardcoded ``loop = 0`` would silently turn every
    finite-loop preview into an infinite one and pass every other test here.
    """
    _require_native()
    utils = import_ext("utils")
    from PIL import Image

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    out_path = tmp_path / "m.webp"
    frames = [Image.new("RGB", (12, 10), c) for c in [(255, 0, 0), (0, 0, 255)]]

    def remux(content: bytes, content_type: str, name: str) -> bytes:
        if out_path.exists():
            out_path.unlink()
        utils._write_preview_content(str(model), content, content_type, name, "")
        return out_path.read_bytes()

    # animated GIF with a finite Netscape loop
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=[50, 60], loop=5)
    assert _webp_anim_loop_count(remux(buf.getvalue(), "image/gif", "a.gif")) == 5

    # animated GIF that loops forever (0) stays 0 (not 1, not dropped)
    buf = io.BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=[50, 60], loop=0)
    assert _webp_anim_loop_count(remux(buf.getvalue(), "image/gif", "a.gif")) == 0

    # animated WebP input: the ANIM loop goes through webp_decode_animation
    buf = io.BytesIO()
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=[50, 60], loop=3)
    assert _webp_anim_loop_count(remux(buf.getvalue(), "image/webp", "a.webp")) == 3


def test_animation_icc_profile_is_preserved(tmp_path):
    """An animated WebP's ICC profile survives the native decode -> re-mux
    (ICCP chunk, byte level). ``decode_animation`` surfaces the profile and
    ``_encode_preview_webp_native`` must hand it to ``webp_encode_animation``;
    dropping it there would shift colours on wide-gamut previews and pass
    every dimension/duration assertion above.
    """
    _require_native()
    utils = import_ext("utils")
    from PIL import Image

    icc = b"audit-icc-profile-payload-for-animation"
    frames = [Image.new("RGB", (14, 11), c) for c in [(200, 10, 10), (10, 200, 10)]]
    buf = io.BytesIO()
    frames[0].save(
        buf,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=[90, 110],
        loop=0,
        icc_profile=icc,
    )
    content = buf.getvalue()
    assert _webp_iccp(content) == icc, "PIL must write the ICCP chunk we preserve"

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    utils._write_preview_content(str(model), content, "image/webp", "anim-icc.webp", "")
    out = (tmp_path / "m.webp").read_bytes()
    assert _webp_iccp(out) == icc, "the re-muxed animation must carry the same ICCP bytes"
    assert _webp_anmf_durations(out) == [90, 110], "durations intact alongside the ICC"


# ---------------------------------------------------------------------------
# Phase 8: the native pipeline is the SINGLE path (no PIL re-encode fallback)
# ---------------------------------------------------------------------------
def test_preview_image_requires_the_native_core(tmp_path, monkeypatch):
    """With no loadable core the image branch raises the actionable
    "native core is unavailable" RuntimeError instead of silently re-encoding
    through PIL (the pre-Phase-8 fallback is gone with the MM_NATIVE switch).
    The tolerant download path turns this into a warning+skip, the editor
    path surfaces it - both are pinned in test_phase6_http.py."""
    native = _reset_native_loader()
    monkeypatch.setattr(native, "core_if_enabled", lambda: None)
    utils = import_ext("utils")
    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="native core is unavailable"):
        utils._write_preview_content(str(model), _gradient_png(16, 12), "image/png", "src.png", "")
    assert not (tmp_path / "m.webp").exists(), "nothing may be written without the core"


def test_native_encode_failure_raises_without_a_pil_retry(tmp_path, monkeypatch):
    """A native encode failure surfaces the historical "Unsupported or corrupt
    preview image" RuntimeError - there is NO PIL second attempt any more (a
    mutation that silently swallowed the native error and re-encoded through
    PIL would pass the pre-Phase-8 suite; this pins the single path)."""
    native = _require_native()
    utils = import_ext("utils")

    mm = native.core_if_enabled()

    def boom(*_a, **_k):
        raise RuntimeError("native encode exploded")

    monkeypatch.setattr(mm, "webp_encode", boom)
    monkeypatch.setattr(mm, "webp_encode_animation", boom)

    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    content = _gradient_png(32, 32)
    with pytest.raises(RuntimeError, match="Unsupported or corrupt preview image"):
        utils._write_preview_content(str(model), content, "image/png", "src.png", "")
    assert not (tmp_path / "m.webp").exists(), "a failed encode must not leave a preview behind"


def test_corrupt_image_raises_the_historical_wording(tmp_path):
    """A corrupt image raises the SAME RuntimeError wording the PIL path used
    (the native pipeline fails inside PIL's decode of the non-WebP input), so
    the tolerant download path still skips it and the editor path still
    surfaces the identical message."""
    _require_native()
    utils = import_ext("utils")
    model = tmp_path / "m.safetensors"
    model.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="Unsupported or corrupt preview image"):
        utils._write_preview_content(str(model), b"not an image at all", "image/png", "x.png", "")


# ---------------------------------------------------------------------------
# the native decode surface is exposed and rejects garbage cleanly
# ---------------------------------------------------------------------------
def test_webp_decode_parity_with_pil():
    """Decode parity (T7 security gate ii): zenwebp's decode matches PIL's on a
    real WebP. A lossless (VP8L) bitstream decodes deterministically, so the
    native RGBA must be byte-identical to both the original and PIL's decode."""
    native = _require_native()
    from PIL import Image

    mm = native.core_if_enabled()
    img = Image.new("RGB", (16, 12))
    px = img.load()
    for y in range(12):
        for x in range(16):
            px[x, y] = ((x * 13 + y * 7) % 256, (x * 5 + y * 11) % 256, (x * y) % 256)
    orig_rgba = img.convert("RGBA").tobytes()

    # native lossless encode -> native decode round-trips byte-exactly
    webp = mm.webp_encode(orig_rgba, 16, 12, b"", 100.0, 6, True)
    rgba_n, wn, hn, _icc = mm.webp_decode(webp)
    assert (wn, hn) == (16, 12)
    assert rgba_n == orig_rgba, "lossless native round trip is byte-exact"

    # ... and PIL decodes the SAME bytes to the SAME pixels (the parity gate)
    rgba_pil = Image.open(io.BytesIO(webp)).convert("RGBA").tobytes()
    assert rgba_n == rgba_pil, "zenwebp decode == PIL/libwebp decode"


def test_webp_decode_rejects_garbage():
    """mm_core.webp_decode maps a corrupt input to a RuntimeError (never a
    panic / hang) - the production face of the L3 webp_decode fuzz target.

    The deterministic malformed inputs MUST raise (a decode that silently
    returned pixels for garbage would defeat the whole guard chain); the
    random bytes only must not crash the interpreter (they cannot be a
    *guaranteed* error - randomness is not assertable).
    """
    native = _require_native()
    mm = native.core_if_enabled()
    for bad in [b"", b"garbage", b"RIFF\x00\x00\x00\x00WEBP", b"RIFF\x24\x00\x00\x00WEBPVP8X" + b"\x00" * 28]:
        with pytest.raises(RuntimeError):
            mm.webp_decode(bad)
    for _ in range(8):
        try:
            mm.webp_decode(os.urandom(64))
        except RuntimeError:
            pass  # expected for essentially every random input
