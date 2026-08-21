from __future__ import annotations

import io
import zipfile
from pathlib import Path

from codemaster.fsutil import Scope
from codemaster.handlers import chain, epub
from codemaster.handlers.base import Blob
from codemaster.kind import classify
from codemaster.scrubber import Edits


def _epub_bytes(with_glyph: bool = True) -> bytes:
    buffer = io.BytesIO()
    body = "<html><body><p>Hello. Note that this is sample."
    if with_glyph:
        body += "\u200b"
    body += "</p></body></html>"
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("content.opf", "<package/>")
        z.writestr("chapter.xhtml", body)
    return buffer.getvalue()


def test_epub_classify() -> None:
    data = _epub_bytes()
    blob = Blob(Path("book.epub"), data, classify(Path("book.epub"), data))
    assert blob.kind == "epub"
    assert any(h.name == "epub" for h in chain(blob))


def test_epub_audit_finds_narration_and_glyph() -> None:
    data = _epub_bytes()
    blob = Blob(Path("book.epub"), data, classify(Path("book.epub"), data))
    kinds = {slip.kind for slip in epub.HANDLER.audit(blob)}
    assert "narration" in kinds
    assert "stealth" in kinds


def test_epub_wash_removes_glyphs_only() -> None:
    data = _epub_bytes()
    blob = Blob(Path("book.epub"), data, classify(Path("book.epub"), data))
    washed, labels = epub.HANDLER.wash(blob, Edits(glyphs=True))
    assert "glyphs" in labels
    with zipfile.ZipFile(io.BytesIO(washed)) as z:
        chapter = z.read("chapter.xhtml").decode("utf-8")
    assert "\u200b" not in chapter


def test_epub_wash_noop_without_glyphs() -> None:
    data = _epub_bytes()
    blob = Blob(Path("book.epub"), data, classify(Path("book.epub"), data))
    washed, labels = epub.HANDLER.wash(blob, Edits(glyphs=False))
    assert labels == []
    assert washed == data


def test_epub_scan_via_portal(tmp_path: Path) -> None:
    from codemaster import portal

    (tmp_path / "book.epub").write_bytes(_epub_bytes())
    ledger = portal.tour([tmp_path], Scope())
    assert len(ledger.sheets) == 1
    assert ledger.sheets[0].marks
