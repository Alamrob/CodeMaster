from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path

import pytest

from codemaster import portal
from codemaster.cli import main
from codemaster.fsutil import Scope
from codemaster.handlers import _deps
from codemaster.report import Grade
from codemaster.scrubber import Edits


def _jpeg_segment(payload: bytes) -> bytes:
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _jpeg_with_meta() -> bytes:
    exif = b"Exif\x00\x00" + b"Software\x00Adobe" + b"\x00" * 20
    xmp = b"http://ns.adobe.com/xap/1.0/\x00" + b"creator:AI tool" + b"\x00" * 20
    iptc = b"Photoshop 3.0\x00" + b"DigitalSourceType" + b"\x00" * 20
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    scan = b"\xff\xda\x00\x0c\x01\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 8
    return (
        b"\xff\xd8"
        + app0
        + _jpeg_segment(exif)
        + _jpeg_segment(xmp)
        + _jpeg_segment(iptc)
        + scan
        + b"\xff\xd9"
    )


def _png_chunk(ctype: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", 0)


def _png_with_text() -> bytes:
    ihdr = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    text = _png_chunk(b"tEXt", b"Software\x00Claude Mark")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + text
        + _png_chunk(b"IEND", b"")
    )


def _docx_blob() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bag:
        bag.writestr(
            "word/document.xml",
            "<w:document><w:p><w:r><w:t>keep in mind this draft</w:t></w:r></w:p></w:document>",
        )
        bag.writestr(
            "docProps/core.xml",
            "<cp:coreProperties><dc:creator>Claude</dc:creator>"
            "<cp:lastModifiedBy>Assistant</cp:lastModifiedBy></cp:coreProperties>",
        )
    return out.getvalue()


def _sheet_blob(pivot: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bag:
        bag.writestr("[Content_Types].xml", "<Types/>")
        bag.writestr(pivot, "<root/>")
        bag.writestr(
            "docProps/core.xml",
            "<cp:coreProperties><dc:creator>OpenAI</dc:creator>"
            "<cp:lastModifiedBy>Claude</cp:lastModifiedBy></cp:coreProperties>",
        )
    return out.getvalue()


def _pdf_blob() -> bytes:
    return b"%PDF-1.4\n/Author (Claude)\n/Producer (OpenAI)\n%%EOF\n"


def test_jpeg_meta_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "shot.jpg"
    path.write_bytes(_jpeg_with_meta())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    kinds = {mark.kind for mark in marks}
    assert {"exif", "xmp", "iptc"} <= kinds
    result = portal.wash_path(path, Edits(meta=True), scope, apply_write=True)
    assert result.altered
    cleaned = path.read_bytes()
    assert b"Exif\x00\x00" not in cleaned
    assert b"http://ns.adobe.com/xap/1.0/" not in cleaned
    assert cleaned.startswith(b"\xff\xd8")


def test_jpeg_keep_meta(tmp_path: Path) -> None:
    path = tmp_path / "shot.jpg"
    path.write_bytes(_jpeg_with_meta())
    result = portal.wash_path(path, Edits(meta=False), Scope(), apply_write=True)
    assert not result.altered


def test_png_text_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "art.png"
    path.write_bytes(_png_with_text())
    scope = Scope()
    kinds = {mark.kind for mark in portal.scan_one(path, scope).marks}
    assert "pngtext" in kinds
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    cleaned = path.read_bytes()
    assert b"tEXt" not in cleaned
    assert cleaned.startswith(b"\x89PNG")


def test_docx_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "draft.docx"
    path.write_bytes(_docx_blob())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(mark.kind == "author" for mark in marks)
    assert any(mark.kind == "narration" for mark in marks)
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    with zipfile.ZipFile(path) as bag:
        core = bag.read("docProps/core.xml").decode()
        body = bag.read("word/document.xml").decode()
    assert "<dc:creator></dc:creator>" in core
    assert "keep in mind" in body


def test_xlsx_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "table.xlsx"
    path.write_bytes(_sheet_blob("xl/workbook.xml"))
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(mark.kind == "author" for mark in marks)
    assert any("openai" in mark.note.lower() for mark in marks)
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    with zipfile.ZipFile(path) as bag:
        core = bag.read("docProps/core.xml").decode()
    assert "<dc:creator></dc:creator>" in core
    assert "<cp:lastModifiedBy></cp:lastModifiedBy>" in core


def test_pptx_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    path.write_bytes(_sheet_blob("ppt/presentation.xml"))
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(mark.kind == "author" for mark in marks)
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    with zipfile.ZipFile(path) as bag:
        core = bag.read("docProps/core.xml").decode()
    assert "OpenAI" not in core
    assert "Claude" not in core


def test_pdf_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    path.write_bytes(_pdf_blob())
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(mark.kind == "pdfkey" for mark in marks)
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    cleaned = path.read_bytes()
    assert b"/Author ()" in cleaned
    assert b"(Claude)" not in cleaned


def test_forensic_report_only(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00\x01Author\x00Creator\x00generated-by\x00" + b"\xff" * 20)
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(mark.kind == "forensic" for mark in marks)
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert not result.altered
    assert path.read_bytes().startswith(b"\x00\x01")


@pytest.mark.skipif(not _deps.pillow_ok(), reason="pillow extra absent")
def test_pixel_mark_detected_and_filled(tmp_path: Path) -> None:
    image_mod = _deps.load("PIL.Image")
    image = image_mod.new("RGB", (64, 64), (200, 200, 200))
    for y in range(56, 64):
        for x in range(56, 64):
            image.putpixel((x, y), (0, 0, 0))
    path = tmp_path / "pic.png"
    image.save(path)
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    assert any(mark.kind == "mark" for mark in marks), [(m.kind, m.note) for m in marks]
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    reopened = image_mod.open(path)
    samples = [reopened.getpixel((x, y)) for x in range(56, 64) for y in range(56, 64)]
    assert sum(sum(pixel) for pixel in samples) / len(samples) > 300


def test_html_audit_and_wash(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    body = (
        "<!DOCTYPE html>\n"
        "<html><head>"
        '<meta name="generator" content="Claude">'
        "</head><body><!-- made by claude -->"
        "<p>as an ai assistant I wrote this</p></body></html>"
    )
    path.write_text(body, encoding="utf-8")
    scope = Scope()
    marks = portal.scan_one(path, scope).marks
    kinds = {mark.kind for mark in marks}
    assert "metatag" in kinds
    assert "comment" in kinds
    result = portal.wash_path(path, Edits(), scope, apply_write=True)
    assert result.altered
    cleaned = path.read_text(encoding="utf-8")
    assert "<!--" not in cleaned
    assert 'name="generator"' not in cleaned


def test_tour_mixed_directory(tmp_path: Path) -> None:
    (tmp_path / "clean.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "shot.jpg").write_bytes(_jpeg_with_meta())
    (tmp_path / "doc.pdf").write_bytes(_pdf_blob())
    ledger = portal.tour([tmp_path], Scope())
    kinds = {mark.kind for sheet in ledger.sheets for mark in sheet.marks}
    assert {"exif", "pdfkey"} <= kinds
    assert ledger.worst() is Grade.DANGER


def test_identify_command(capsys, tmp_path: Path) -> None:
    (tmp_path / "shot.jpg").write_bytes(_jpeg_with_meta())
    assert main(["identify", "--json", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    row = payload[0]
    assert row["kind"] == "image"
    assert "meta" in row["handlers"]
    assert row["marks"] >= 3


def test_scan_json_new_kinds(capsys, tmp_path: Path) -> None:
    (tmp_path / "doc.pdf").write_bytes(_pdf_blob())
    assert main(["scan", "--json", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worst"] == "danger"
