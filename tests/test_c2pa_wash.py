from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import image_meta as im

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIREFLY = (
    _REPO_ROOT
    / "remove-ai-watermarks-main"
    / "data"
    / "fixtures"
    / "provenance"
    / "firefly-1.png"
)
_FLUX = (
    _REPO_ROOT
    / "remove-ai-watermarks-main"
    / "data"
    / "fixtures"
    / "provenance"
    / "flux-1.jpg"
)


def _jpeg_segment(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def _jpeg_with_c2pa_app11() -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    c2pa = b"JP\x02\x11\x00\x00\x00\x01" + b"jumb" + b"c2pa" + b"\x00" * 16
    scan = b"\xff\xda\x00\x0c\x01\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 8
    return b"\xff\xd8" + app0 + _jpeg_segment(0xEB, c2pa) + scan + b"\xff\xd9"


def _png_chunk(ctype: str, body: bytes) -> bytes:
    name = ctype.encode("latin-1")
    return (
        struct.pack(">I", len(body))
        + name
        + body
        + struct.pack(">I", zlib.crc32(name + body) & 0xFFFFFFFF)
    )


def _png_with_cabx() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    body = b"jumb\x00\x00\x00\x02jumb" + b"c2pa.contentcredentials" + b"\x00" * 8
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk("IHDR", ihdr)
        + _png_chunk("caBX", body)
        + _png_chunk("IEND", b"")
    )


def test_jpeg_audit_flags_c2pa_app_segment() -> None:
    slips = im._jpeg_audit(_jpeg_with_c2pa_app11())
    assert any(s.kind == "c2pa" and "c2pa" in s.note for s in slips)


def test_jpeg_wash_removes_c2pa_app_segment() -> None:
    data = _jpeg_with_c2pa_app11()
    washed, notes = im._jpeg_wash(data)
    assert notes == ["meta"]
    assert washed != data
    assert b"c2pa" not in washed
    assert b"jumb" not in washed
    assert washed.startswith(b"\xff\xd8")
    assert b"\xff\xda" in washed


def test_png_audit_flags_cabx_chunk() -> None:
    slips = im._png_audit(_png_with_cabx())
    assert any(s.kind == "c2pa" and "caBX" in s.note for s in slips)


def test_png_wash_removes_cabx_chunk() -> None:
    data = _png_with_cabx()
    washed, notes = im._png_wash(data)
    assert notes == ["meta"]
    assert washed != data
    assert b"caBX" not in washed
    assert b"jumb" not in washed
    assert washed.startswith(b"\x89PNG")
    assert b"IEND" in washed


@pytest.mark.skipif(not _FIREFLY.exists(), reason="C2PA reference fixture absent")
def test_firefly_fixture_wash_removes_c2pa() -> None:
    data = _FIREFLY.read_bytes()
    washed, notes = im._png_wash(data)
    assert notes == ["meta"]
    assert b"caBX" not in washed
    assert b"c2pa" not in washed


@pytest.mark.skipif(not _FLUX.exists(), reason="C2PA reference fixture absent")
def test_flux_fixture_wash_removes_c2pa() -> None:
    data = _FLUX.read_bytes()
    washed, notes = im._jpeg_wash(data)
    assert notes == ["meta"]
    assert b"c2pa" not in washed
    assert b"jumb" not in washed


@pytest.mark.skipif(not _FIREFLY.exists(), reason="C2PA reference fixture absent")
def test_firefly_wash_leaves_audit_clean(tmp_path: Path) -> None:
    path = tmp_path / "firefly.png"
    washed, _ = im._png_wash(_FIREFLY.read_bytes())
    path.write_bytes(washed)
    marks = portal.scan_one(path, Scope()).marks
    assert not any(m.kind == "c2pa" for m in marks)
