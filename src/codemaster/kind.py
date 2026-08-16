from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".pyw",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".md",
        ".rst",
        ".txt",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sh",
        ".ps1",
        ".bat",
        ".sql",
        ".xml",
        ".svg",
        ".csv",
        ".log",
    }
)

IMAGE_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
        ".heic",
        ".heif",
        ".avif",
    }
)

_ISOBMFF_BRANDS = frozenset(
    {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"heim",
        b"heis",
        b"hevm",
        b"hevs",
        b"mif1",
        b"msf1",
        b"avif",
        b"avis",
    }
)


def classify(
    path: Path,
    data: bytes,
    text_suffixes: frozenset[str] = TEXT_SUFFIXES,
) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if data.startswith(b"\xff\xd8\xff"):
        return "image"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image"
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return "image"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _ISOBMFF_BRANDS:
        return "image"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        head = data[:2048]
        if b"word/document.xml" in head:
            return "docx"
        if b"xl/workbook.xml" in head and b"[Content_Types].xml" in head:
            return "xlsx"
        if b"ppt/presentation.xml" in head and b"[Content_Types].xml" in head:
            return "pptx"
        return "zip"
    head = data[:512].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "html"
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if b"\x00" in data:
        return "binary"
    if suffix in text_suffixes:
        return "text"
    if _printable_ratio(data) >= 0.9:
        return "text"
    return "binary"


def _printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    sample = data[:8192]
    printable = sum(1 for byte in sample if byte in (9, 10, 13) or 32 <= byte <= 126)
    return printable / len(sample)
