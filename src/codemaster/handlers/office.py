from __future__ import annotations

import io
import re
import zipfile

from codemaster import signatures, unicode
from codemaster.handlers.base import Blob, Handler, line_of
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits

_TEXT_ENTRY = "word/document.xml"
_CORE_ENTRIES = ("docProps/core.xml", "word/core.xml")
_TAG_RE = re.compile(r"<[^>]*>")
_CREATOR_RE = re.compile(
    r"<([A-Za-z]+:)?(creator|lastModifiedBy)>(.*?)</(?:\1)?\2>", re.IGNORECASE
)


class _OfficeHandler:
    name = "office"

    def probe(self, blob: Blob) -> bool:
        return blob.kind in ("docx", "xlsx", "pptx")

    def audit(self, blob: Blob) -> list[Slip]:
        slips: list[Slip] = []
        try:
            with zipfile.ZipFile(io.BytesIO(blob.data)) as bag:
                names = bag.namelist()
                if _TEXT_ENTRY in names:
                    text = bag.read(_TEXT_ENTRY).decode("utf-8", errors="replace")
                    body = _TAG_RE.sub(" ", text)
                    slips.extend(signatures.match(body))
                    slips.extend(unicode.probe(text))
                for entry in _CORE_ENTRIES:
                    if entry not in names:
                        continue
                    text = bag.read(entry).decode("utf-8", errors="replace")
                    for match in _CREATOR_RE.finditer(text):
                        if match.group(3).strip():
                            slips.append(
                                Slip(
                                    line_of(text, match.start()),
                                    1,
                                    "author",
                                    match.group(3)[:40],
                                    Grade.DANGER,
                                )
                            )
        except (zipfile.BadZipFile, OSError):
            pass
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        labels: list[str] = []
        out = io.BytesIO()
        try:
            with (
                zipfile.ZipFile(io.BytesIO(blob.data)) as bag,
                zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
            ):
                for info in bag.infolist():
                    raw = bag.read(info.filename)
                    if info.filename == _TEXT_ENTRY and edits.glyphs:
                        text = raw.decode("utf-8", errors="replace")
                        raw = unicode.flush(text).encode("utf-8")
                        labels.append("glyphs")
                    elif info.filename in _CORE_ENTRIES and edits.meta:
                        text = raw.decode("utf-8", errors="replace")
                        raw = _blank_creators(text).encode("utf-8")
                        labels.append("author")
                    target.writestr(info, raw)
        except (zipfile.BadZipFile, OSError):
            return blob.data, []
        return out.getvalue(), labels


HANDLER: Handler = _OfficeHandler()


def _blank_creators(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        tag = match.group(2)
        return f"<{prefix}{tag}></{prefix}{tag}>"

    return _CREATOR_RE.sub(replace, text)
