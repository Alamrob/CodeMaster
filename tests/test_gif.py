from __future__ import annotations

import io
from pathlib import Path

import pytest

from codemaster import portal
from codemaster.fsutil import Scope
from codemaster.handlers import _deps
from codemaster.handlers import image_meta as im
from codemaster.scrubber import Edits


def _gif_with_meta() -> bytes:
    body = io.BytesIO()
    body.write(b"GIF89a")
    body.write(b"\x01\x00\x01\x00\x80\x00\x00")
    body.write(b"\x00\x00\x00\xff\xff\xff")
    body.write(b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00")
    body.write(b"\x02")
    body.write(b"\x02\x44\x01\x00")
    comment = b"made with midjourney"
    body.write(b"\x21\xfe" + bytes([len(comment)]) + comment + b"\x00")
    xmp = b"<x:xmpmeta>AI</x:xmpmeta>"
    body.write(b"\x21\xff\x0b" + b"XMP DataXMP" + bytes([len(xmp)]) + xmp + b"\x00")
    body.write(b"\x3b")
    return body.getvalue()


def test_gif_audit_flags_comment_and_xmp() -> None:
    slips = im._gif_audit(_gif_with_meta())
    kinds = [s.kind for s in slips]
    notes = [s.note for s in slips]
    assert "comment" in kinds
    assert "xmp" in kinds
    assert any("gif comment" in n for n in notes)
    assert any("gif xmp" in n for n in notes)


def test_gif_wash_removes_meta_and_keeps_frame() -> None:
    data = _gif_with_meta()
    washed, notes = im._gif_wash(data)
    assert notes == ["meta"]
    assert washed != data
    assert b"midjourney" not in washed
    assert b"XMP DataXMP" not in washed
    assert washed.startswith(b"GIF89a")
    assert washed.endswith(b"\x3b")


def test_gif_wash_clean_is_noop() -> None:
    data = bytearray(_gif_with_meta())
    start = data.find(b"\x21\xfe")
    assert start != -1
    del data[start : start + 2 + len(b"made with midjourney") + 1]
    start = data.find(b"\x21\xff")
    assert start != -1
    del data[start : start + 2 + 11 + len(b"<x:xmpmeta>AI</x:xmpmeta>") + 1]
    cleaned = bytes(data)
    washed, notes = im._gif_wash(cleaned)
    assert notes == []
    assert washed == cleaned


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_gif_wash_keeps_decodable() -> None:
    from PIL import Image

    data = _gif_with_meta()
    with Image.open(io.BytesIO(data)) as opened:
        opened.verify()
    washed, _ = im._gif_wash(data)
    with Image.open(io.BytesIO(washed)) as reopened:
        reopened.verify()


def test_gif_portal_scan_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "pic.gif"
    path.write_bytes(_gif_with_meta())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(m.kind in ("comment", "xmp") for m in marks)
    result = portal.wash_path(path, Edits(meta=True), scope, apply_write=True)
    assert result.altered
    assert b"XMP DataXMP" not in path.read_bytes()
