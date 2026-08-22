from __future__ import annotations

import struct
from pathlib import Path

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import chain, media
from codemaster.handlers.base import Blob
from codemaster.kind import classify
from codemaster.scrubber import Edits


def _box(btype: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + btype + payload


def _mp4_with_c2pa() -> bytes:
    c2pa = _box(b"uuid", b"jumb" + b"\x00" * 4 + b"c2pa.contentcredentials")
    meta = _box(b"meta", b"\x00\x00\x00\x00" + c2pa)
    return _box(b"ftyp", b"mp42\x00\x00\x00\x00") + _box(b"moov", meta)


def test_classify_video() -> None:
    data = _mp4_with_c2pa()
    assert classify(Path("clip.mp4"), data) == "video"


def test_video_audit_finds_c2pa() -> None:
    data = _mp4_with_c2pa()
    blob = Blob(Path("clip.mp4"), data, classify(Path("clip.mp4"), data))
    assert any(h.name == "media" for h in chain(blob))
    kinds = {s.kind for s in media.HANDLER.audit(blob)}
    assert "c2pa" in kinds


def test_video_wash_zeroes_meta() -> None:
    data = _mp4_with_c2pa()
    blob = Blob(Path("clip.mp4"), data, classify(Path("clip.mp4"), data))
    washed, labels = media.HANDLER.wash(blob, Edits())
    assert "meta" in labels
    assert b"c2pa" not in washed


def test_classify_audio_and_markers() -> None:
    aud = (
        b"ID3\x04\x00\x00\x00\x00\x00\x00"
        + b"TIT2\x00\x00\x00\x08\x00\x00\x00sora demo"
        + b"\xff\xfb\x90\x00\x00"
    )
    assert classify(Path("track.mp3"), aud) == "audio"
    blob = Blob(Path("track.mp3"), aud, "audio")
    kinds = {s.kind for s in media.HANDLER.audit(blob)}
    assert "model" in kinds or "marker" in kinds


def test_classify_model_gguf() -> None:
    assert classify(Path("model.gguf"), b"GGUF" + b"qwen" * 40) == "model"


def test_audio_wash_noop() -> None:
    aud = b"ID3\x04\x00" + b"\xff\xfb\x90\x00\x00"
    blob = Blob(Path("t.mp3"), aud, "audio")
    washed, labels = media.HANDLER.wash(blob, Edits())
    assert labels == []
    assert washed == aud


def test_media_via_portal(tmp_path: Path) -> None:
    (tmp_path / "clip.mp4").write_bytes(_mp4_with_c2pa())
    ledger = portal.tour([tmp_path], Scope())
    assert len(ledger.sheets) == 1
    assert ledger.sheets[0].marks


def test_lsb_stego_flat_zero() -> None:
    from codemaster.handlers import _deps, image_pixels

    PIL = _deps.load("PIL.Image")
    if not PIL:
        import pytest

        pytest.skip("PIL absent")
    image = PIL.new("L", (256, 256), 100)
    assert image_pixels._lsb_stego_score(image) == 0.0


def test_lsb_stego_random_detects() -> None:
    import io

    from codemaster.handlers import _deps, image_pixels
    from codemaster.handlers.base import Blob

    np = _deps.load("numpy")
    PIL = _deps.load("PIL.Image")
    if not np or not PIL:
        import pytest

        pytest.skip("numpy/PIL absent")
    arr = np.full((256, 256), 100, np.uint8)
    rng = np.random.default_rng(7)
    arr[::2, ::2] = 100 + rng.integers(0, 2, (128, 128))
    image = PIL.fromarray(arr)
    score = image_pixels._lsb_stego_score(image)
    assert score is not None and score > 0.1
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    blob = Blob(Path("x.png"), buffer.getvalue(), "image")
    assert any(s.kind == "stego" for s in image_pixels.HANDLER.audit(blob))
