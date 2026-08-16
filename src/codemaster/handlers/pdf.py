from __future__ import annotations

import re

from codemaster import signatures
from codemaster.handlers.base import Blob, Handler
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits

_KEYS = ("Author", "Creator", "Producer", "Title", "Subject", "Keywords")
_KEY_RE = re.compile(
    rb"/(" + b"|".join(key.encode() for key in _KEYS) + rb")\s*\(([^)]*)\)"
)
_WASH_RE = re.compile(
    rb"/(" + b"|".join(key.encode() for key in _KEYS[:4]) + rb")\s*\([^)]*\)"
)
_META_MARKERS = (
    b"c2pa",
    b"jumbf",
    b"ContentCredentials",
    b"xmp",
    b"generator",
    b"synthid",
)


class _PdfHandler:
    name = "pdf"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "pdf"

    def audit(self, blob: Blob) -> list[Slip]:
        data = blob.data
        slips: list[Slip] = []
        for match in _KEY_RE.finditer(data):
            value = match.group(2)
            if not value:
                continue
            slips.append(
                Slip(
                    1,
                    match.start() + 1,
                    "pdfkey",
                    f"{match.group(1).decode()}={value[:48].decode(errors='replace')}",
                    Grade.DANGER,
                )
            )
        for marker in _META_MARKERS:
            index = data.find(marker)
            if index != -1:
                slips.append(
                    Slip(
                        1,
                        index + 1,
                        "pdfmeta",
                        marker.decode(errors="replace"),
                        Grade.SIGNAL,
                    )
                )
        slips.extend(signatures.match(_extract_strings(data)))
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        if not edits.meta:
            return blob.data, []
        cleaned, count = _WASH_RE.subn(lambda m: b"/" + m.group(1) + b" ()", blob.data)
        if count:
            return cleaned, ["pdfkeys"]
        return blob.data, []


HANDLER: Handler = _PdfHandler()


def _extract_strings(data: bytes) -> str:
    runs: list[str] = []
    current: list[int] = []
    for byte in data:
        if byte in (9, 10, 13) or 32 <= byte <= 126:
            current.append(byte)
        else:
            if len(current) >= 5:
                runs.append(bytes(current).decode("latin-1"))
            current = []
    if len(current) >= 5:
        runs.append(bytes(current).decode("latin-1"))
    return "\n".join(runs)
