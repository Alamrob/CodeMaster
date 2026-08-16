from __future__ import annotations

from pathlib import Path

from codemaster.kind import classify


def _classify(tmp_path: Path, name: str, data: bytes) -> str:
    return classify(tmp_path / name, data)


def test_png_kind(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.png", b"\x89PNG\r\n\x1a\nrest") == "image"


def test_jpeg_kind(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.jpg", b"\xff\xd8\xff\xe0") == "image"


def test_pdf_kind(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.pdf", b"%PDF-1.4\n") == "pdf"


def test_docx_kind(tmp_path: Path) -> None:
    data = b"PK\x03\x04" + b"word/document.xml" + b"tail"
    assert _classify(tmp_path, "x.docx", data) == "docx"


def test_xlsx_kind(tmp_path: Path) -> None:
    data = b"PK\x03\x04" + b"[Content_Types].xmlxl/workbook.xml" + b"tail"
    assert _classify(tmp_path, "x.xlsx", data) == "xlsx"


def test_pptx_kind(tmp_path: Path) -> None:
    data = b"PK\x03\x04" + b"[Content_Types].xmlppt/presentation.xml" + b"tail"
    assert _classify(tmp_path, "x.pptx", data) == "pptx"


def test_plain_zip_is_zip(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.zip", b"PK\x03\x04nothing") == "zip"


def test_html_kind(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.html", b"<!DOCTYPE html>\n<body>") == "html"


def test_known_text_suffix(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.py", b"def f():\n    return 1\n") == "text"


def test_printable_unknown_suffix(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.weird", b"just words here nothing else") == "text"


def test_binary_with_nul(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.bin", b"\x00\x01\x02Author\x00\xff") == "binary"


def test_binary_low_printable(tmp_path: Path) -> None:
    assert _classify(tmp_path, "x.bin", b"\x00\x80\xff" * 100) == "binary"
