from __future__ import annotations

import io
from pathlib import Path

import pytest

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import _deps
from codemaster.scrubber import Edits


def _png_bytes() -> bytes:
    image = _deps.load("PIL.Image")
    buf = io.BytesIO()
    image.new("RGB", (8, 8)).save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_verify_rolls_back_broken_post() -> None:
    pre = _png_bytes()
    assert portal._verify_wash_image(pre, b"\x00\x01garbage") == pre


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_verify_keeps_valid_post() -> None:
    pre = _png_bytes()
    assert portal._verify_wash_image(pre, pre) is None


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_verify_skips_non_decodable_input() -> None:
    assert portal._verify_wash_image(b"\x00\x01garbage", b"\x00\x01garbage") is None


def test_verify_skips_without_pillow(monkeypatch) -> None:
    monkeypatch.setattr(_deps, "pillow_ok", lambda: False)
    assert portal._verify_wash_image(b"\x89PNG", b"\x89PNG") is None


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
@pytest.mark.skipif(not _deps.piexif_ok(), reason="piexif extra absent")
def test_wash_path_keeps_real_jpeg_decodable(tmp_path: Path) -> None:
    image = _deps.load("PIL.Image")
    piexif = _deps.load("piexif")
    tags = {
        "0th": {piexif.ImageIFD.Software: b"Adobe Firefly"},
        "Exif": {},
        "GPS": {},
        "Interop": {},
        "1st": {},
        "thumbnail": None,
    }
    buf = io.BytesIO()
    image.new("RGB", (16, 16)).save(buf, "JPEG", exif=piexif.dump(tags))
    path = tmp_path / "shot.jpg"
    path.write_bytes(buf.getvalue())
    result = portal.wash_path(path, Edits(meta=True), Scope(), apply_write=True)
    assert result.altered
    with image.open(path) as reopened:
        reopened.verify()
    assert b"Software" not in path.read_bytes()
