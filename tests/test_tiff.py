from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import _deps
from codemaster.handlers import image_meta as im
from codemaster.kind import classify
from codemaster.scrubber import Edits


def _tiff(
    order: bytes,
    software: str = "Adobe Firefly 3",
    artist: str = "Artist X",
    xmp: bytes | None = None,
) -> bytes:
    end = "<" if order == b"II" else ">"
    tags: list[tuple[int, bytes]] = [
        (305, software.encode() + b"\x00"),
        (315, artist.encode() + b"\x00"),
    ]
    if xmp is not None:
        tags.append((700, xmp))
    table = struct.pack(end + "H", len(tags))
    blob_pos = 8 + 2 + 12 * len(tags) + 4
    entries: list[tuple[int, int, int, int]] = []
    for number, value in tags:
        entries.append((number, 2, len(value), blob_pos))
        blob_pos += len(value)
    for number, ftype, count, offset in entries:
        table += struct.pack(end + "HHI", number, ftype, count)
        table += struct.pack(end + "I", offset)
    table += struct.pack(end + "I", 0)
    blob = b"".join(value for _, value in tags)
    return order + struct.pack(end + "H", 42) + struct.pack(end + "I", 8) + table + blob


def _real_tiff(software: str = "Adobe Firefly 3") -> bytes:
    value = software.encode() + b"\x00"
    count = 10
    blob_pos = 8 + 2 + 12 * count + 4
    pixel_off = blob_pos + len(value)
    entries = [
        (256, 4, 1, 1),
        (257, 4, 1, 1),
        (258, 4, 1, 8),
        (259, 4, 1, 1),
        (262, 4, 1, 1),
        (273, 4, 1, pixel_off),
        (277, 4, 1, 1),
        (278, 4, 1, 1),
        (279, 4, 1, 1),
        (305, 2, len(value), blob_pos),
    ]
    out = bytearray(b"II*\x00")
    out += struct.pack("<I", 8)
    out += struct.pack("<H", len(entries))
    for num, ftype, cnt, val in entries:
        out += struct.pack("<HHI", num, ftype, cnt)
        out += struct.pack("<I", val)
    out += struct.pack("<I", 0)
    out += value
    out += b"\x00\x00\x00\x80"
    return bytes(out)


def test_tiff_audit_flags_software_and_xmp() -> None:
    slips = im._tiff_audit(_tiff(b"II", xmp=b"<xmpmeta>stuff</xmpmeta>"))
    kinds = [s.kind for s in slips]
    notes = [s.note for s in slips]
    assert "exif" in kinds
    assert "xmp" in kinds
    assert any("tiff software" in n for n in notes)
    assert any("firefly" in n.lower() for n in notes)


def test_tiff_audit_big_endian() -> None:
    slips = im._tiff_audit(_tiff(b"MM"))
    assert any("firefly" in s.note.lower() for s in slips)


def test_tiff_wash_removes_software_and_xmp() -> None:
    data = _real_tiff()
    washed, notes = im._tiff_wash(data)
    assert notes == ["meta"]
    assert washed != data
    lowered = washed.lower()
    assert b"firefly" not in lowered
    assert b"xmp" not in lowered
    assert washed.startswith(b"II*\x00")


def test_tiff_wash_clean_is_noop() -> None:
    data = _real_tiff(software="plain editor")
    washed, notes = im._tiff_wash(data)
    assert notes == []
    assert washed == data


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_tiff_wash_keeps_decodable_on_real_file() -> None:
    from PIL import Image

    data = _real_tiff()
    washed, _ = im._tiff_wash(data)
    with Image.open(io.BytesIO(washed)) as reopened:
        reopened.verify()
    with Image.open(io.BytesIO(data)) as original:
        original.verify()


def test_tiff_portal_scan_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "pic.tiff"
    path.write_bytes(_real_tiff())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any("firefly" in m.note.lower() for m in marks)
    result = portal.wash_path(path, Edits(meta=True), scope, apply_write=True)
    assert result.altered
    lowered = path.read_bytes().lower()
    assert b"firefly" not in lowered
    assert b"xmp" not in lowered


def test_heic_kind(tmp_path: Path) -> None:
    data = b"\x00\x00\x00\x20ftypheic" + b"\x00" * 40
    assert classify(tmp_path / "x.heic", data) == "image"


def test_avif_kind(tmp_path: Path) -> None:
    data = b"\x00\x00\x00\x20ftypavif" + b"\x00" * 40
    assert classify(tmp_path / "x.avif", data) == "image"


def test_other_ftyp_is_not_image(tmp_path: Path) -> None:
    data = b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 40
    assert classify(tmp_path / "x.mp4", data) != "image"
