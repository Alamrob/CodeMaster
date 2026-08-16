from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

import pytest

from codemaster import portal
from codemaster._internal import rich
from codemaster.fsutil import Scope
from codemaster.handlers import _deps
from codemaster.report import Grade

_REPO_ROOT = Path(__file__).resolve().parents[1]
_C2PA_FIXTURE = (
    _REPO_ROOT
    / "remove-ai-watermarks-main"
    / "data"
    / "fixtures"
    / "provenance"
    / "firefly-1.png"
)


def _chunk(ctype: str, body: bytes) -> bytes:
    name = ctype.encode("latin-1")
    return (
        struct.pack(">I", len(body))
        + name
        + body
        + struct.pack(">I", zlib.crc32(name + body) & 0xFFFFFFFF)
    )


def _tiny_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk("IHDR", ihdr) + _chunk("IEND", b"")


def _exif_dict() -> dict:
    piexif = _deps.load("piexif")
    return {
        "0th": {
            piexif.ImageIFD.Software: b"Adobe Photoshop Firefly AI 25.0",
            piexif.ImageIFD.Artist: b"DALL-E",
        },
        "Exif": {
            piexif.ExifIFD.UserComment: b"made with stable diffusion",
        },
        "GPS": {},
        "Interop": {},
        "1st": {},
        "thumbnail": None,
    }


def _jpeg_with_exif() -> bytes:
    image = _deps.load("PIL.Image")
    piexif = _deps.load("piexif")
    buf = io.BytesIO()
    image.new("RGB", (16, 16)).save(buf, "JPEG", exif=piexif.dump(_exif_dict()))
    return buf.getvalue()


@pytest.mark.skipif(not _deps.piexif_ok(), reason="piexif extra absent")
def test_exif_pairs_decodes_ai_tags() -> None:
    piexif = _deps.load("piexif")
    pairs = rich.exif_pairs(piexif.dump(_exif_dict()))
    assert ("0th.Software", "Adobe Photoshop Firefly AI 25.0") in pairs
    assert ("0th.Artist", "DALL-E") in pairs
    assert any(name == "Exif.UserComment" for name, _ in pairs)


@pytest.mark.skipif(not _deps.piexif_ok(), reason="piexif extra absent")
def test_exif_pairs_garbage_returns_empty() -> None:
    assert rich.exif_pairs(b"Exif\x00\x00" + b"not a tiff header") == []


def test_c2pa_info_none_on_clean_png() -> None:
    assert rich.c2pa_info(_tiny_png()) is None


@pytest.mark.skipif(not _deps.piexif_ok(), reason="piexif extra absent")
@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_jpeg_exif_value_slips_are_danger(tmp_path: Path) -> None:
    path = tmp_path / "shot.jpg"
    path.write_bytes(_jpeg_with_exif())
    marks = portal.scan_one(path, Scope()).marks
    hits = [m for m in marks if m.kind == "exif" and "Firefly" in m.note]
    assert hits and all(m.rank is Grade.DANGER for m in hits)


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _C2PA_FIXTURE.exists(), reason="C2PA reference fixture absent")
def test_c2pa_info_reads_reference_fixture() -> None:
    info = rich.c2pa_info(_C2PA_FIXTURE.read_bytes())
    assert info is not None
    assert "Firefly" in info["generator"]
    assert info["ai"] is True
    assert info["state"] == "Valid"


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _C2PA_FIXTURE.exists(), reason="C2PA reference fixture absent")
def test_c2pa_audit_reports_generator_slips(tmp_path: Path) -> None:
    path = tmp_path / _C2PA_FIXTURE.name
    path.write_bytes(_C2PA_FIXTURE.read_bytes())
    marks = portal.scan_one(path, Scope()).marks
    notes = [m.note for m in marks if m.kind == "c2pa"]
    assert any("generator: Adobe_Firefly" in note for note in notes)
    assert any("source: AI-generated" in note for note in notes)
