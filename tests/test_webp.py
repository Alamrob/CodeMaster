from __future__ import annotations

import struct
from pathlib import Path

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import image_meta as im
from codemaster.scrubber import Edits


def _riff_chunk(fourcc: bytes, payload: bytes) -> bytes:
    pad = b"\x00" if len(payload) % 2 else b""
    return fourcc + struct.pack("<I", len(payload)) + payload + pad


def _webp_with_c2pa() -> bytes:
    vp8 = _riff_chunk(b"VP8L", b"\x2f\x00\x00\x00" + b"\x00" * 20)
    c2pa = _riff_chunk(
        b"C2PA",
        b"\x00\x00\x00jumb\x00\x00\x00\x00c2pa.contentcredentials" + b"\x00" * 30,
    )
    exif = _riff_chunk(
        b"EXIF", b"II*\x00" + b"Software\x00Adobe Firefly" + b"\x00" * 12
    )
    inner = vp8 + c2pa + exif
    return b"RIFF" + struct.pack("<I", 4 + len(inner)) + b"WEBP" + inner


def test_webp_audit_flags_c2pa() -> None:
    slips = im._riff_audit(_webp_with_c2pa())
    assert any(s.kind == "c2pa" and "C2PA" in s.note for s in slips)


def test_webp_audit_flags_exif_meta() -> None:
    slips = im._riff_audit(_webp_with_c2pa())
    assert any(s.kind == "meta" and "EXIF" in s.note for s in slips)


def test_webp_wash_removes_c2pa_and_exif_keeps_image() -> None:
    data = _webp_with_c2pa()
    washed, notes = im._riff_wash(data)
    assert notes == ["meta"]
    assert washed != data
    assert b"C2PA" not in washed
    assert b"EXIF" not in washed
    assert b"c2pa" not in washed
    assert b"VP8L" in washed
    assert struct.unpack("<I", washed[4:8])[0] == len(washed) - 8


def test_webp_keep_when_clean() -> None:
    vp8 = _riff_chunk(b"VP8L", b"\x2f\x00\x00\x00" + b"\x00" * 20)
    inner = vp8
    data = b"RIFF" + struct.pack("<I", 4 + len(inner)) + b"WEBP" + inner
    washed, notes = im._riff_wash(data)
    assert notes == []
    assert washed == data


def test_webp_portal_scan_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "pic.webp"
    path.write_bytes(_webp_with_c2pa())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(m.kind == "c2pa" for m in marks)
    result = portal.wash_path(path, Edits(meta=True), scope, apply_write=True)
    assert result.altered
    cleaned = path.read_bytes()
    assert b"C2PA" not in cleaned
    assert b"VP8L" in cleaned
