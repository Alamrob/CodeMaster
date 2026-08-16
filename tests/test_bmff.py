from __future__ import annotations

import struct
from pathlib import Path

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import image_meta as im
from codemaster.kind import classify
from codemaster.scrubber import Edits


def _box(btype: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + btype + payload


def _fullbox(btype: bytes, payload: bytes) -> bytes:
    return _box(btype, b"\x00\x00\x00\x00" + payload)


def _avif_with_meta() -> bytes:
    ftyp = _box(b"ftyp", b"avif" + struct.pack(">I", 0) + b"avifmif1")
    uuid_xmp = _box(b"uuid", im._BMFF_XMP_UUID + b"<x:xmpmeta>xpacket AI</x:xmpmeta>")
    uuid_c2pa = _box(b"uuid", b"jumb" + b"\x00" * 8 + b"c2pa.contentcredentials")
    exif = _box(b"Exif", b"II*\x00" + b"Software\x00Adobe Firefly" + b"\x00" * 8)
    meta = _fullbox(b"meta", _box(b"hdlr", b"\x00" * 24) + uuid_xmp + uuid_c2pa + exif)
    mdat = _box(b"mdat", b"AV01" + b"\x00" * 40)
    return ftyp + meta + mdat


def _avif_clean() -> bytes:
    ftyp = _box(b"ftyp", b"avif" + struct.pack(">I", 0) + b"avifmif1")
    meta = _fullbox(b"meta", _box(b"hdlr", b"\x00" * 24))
    mdat = _box(b"mdat", b"AV01" + b"\x00" * 40)
    return ftyp + meta + mdat


def test_bmff_kind() -> None:
    assert classify(Path("x.avif"), _avif_with_meta()) == "image"


def test_bmff_scan_finds_xmp_exif_c2pa() -> None:
    labels = [btype.decode() for btype, _, _ in im._bmff_scan(_avif_with_meta())]
    assert "uuid" in labels
    assert "Exif" in labels


def test_bmff_audit_flags_kinds() -> None:
    slips = im._bmff_audit(_avif_with_meta())
    kinds = {s.kind for s in slips}
    assert "xmp" in kinds
    assert "exif" in kinds
    assert "c2pa" in kinds


def test_bmff_wash_zeroes_meta_keeps_structure() -> None:
    data = _avif_with_meta()
    washed, notes = im._bmff_wash(data)
    assert notes == ["meta"]
    assert washed != data
    assert len(washed) == len(data)
    assert washed[:8] == data[:8]
    assert b"contentcredentials" not in washed
    assert b"Firefly" not in washed
    assert b"x:xmpmeta" not in washed


def test_bmff_wash_clean_is_noop() -> None:
    data = _avif_clean()
    washed, notes = im._bmff_wash(data)
    assert notes == []
    assert washed == data


def test_bmff_portal_scan_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "photo.avif"
    path.write_bytes(_avif_with_meta())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any("Firefly" in m.note or m.kind == "exif" for m in marks)
    result = portal.wash_path(path, Edits(meta=True), scope, apply_write=True)
    assert result.altered
    cleaned = path.read_bytes()
    assert b"Firefly" not in cleaned
    assert b"contentcredentials" not in cleaned
