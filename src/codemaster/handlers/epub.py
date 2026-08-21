from __future__ import annotations

import io
import re
import zipfile

from codemaster import signatures, unicode
from codemaster.handlers.base import Blob, Handler
from codemaster.report import Slip
from codemaster.scrubber import Edits

_XHTML_EXT = re.compile(r"\.(xhtml|html|htm)$", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_GLYPH_LABELS = ("glyphs",)


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub(" ", text)


def _text_parts(data: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return [
                _strip_tags(archive.read(name).decode("utf-8", errors="replace"))
                for name in archive.namelist()
                if _XHTML_EXT.search(name)
            ]
    except (OSError, zipfile.BadZipFile, ValueError):
        return []


def _remove_glyphs(text: str) -> tuple[str, bool]:
    spans = unicode.stealth_ranges(text)
    if not spans:
        return text, False
    out = []
    cursor = 0
    for start, end in spans:
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return "".join(out), True


class _EpubHandler:
    name = "epub"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "epub"

    def audit(self, blob: Blob) -> list[Slip]:
        slips: list[Slip] = []
        for text in _text_parts(blob.data):
            slips.extend(unicode.probe(text))
            slips.extend(signatures.match(text))
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        if not edits.glyphs:
            return blob.data, []
        try:
            archive = zipfile.ZipFile(io.BytesIO(blob.data))
        except (OSError, zipfile.BadZipFile, ValueError):
            return blob.data, []
        labels: list[str] = []
        with archive:
            parts: list[tuple[str, bytes]] = []
            for name in archive.namelist():
                payload = archive.read(name)
                if not _XHTML_EXT.search(name):
                    parts.append((name, payload))
                    continue
                raw = payload.decode("utf-8", errors="replace")
                cleaned, changed = _remove_glyphs(raw)
                if changed:
                    labels.append("glyphs")
                parts.append((name, cleaned.encode("utf-8")))
        if not labels:
            return blob.data, []
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
            for name, payload in parts:
                out.writestr(name, payload)
        return buffer.getvalue(), sorted(set(labels))


HANDLER: Handler = _EpubHandler()
