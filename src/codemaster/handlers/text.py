from __future__ import annotations

from codemaster import signatures, tokens, unicode
from codemaster.handlers.base import Blob, Handler
from codemaster.report import Slip
from codemaster.scrubber import Edits, scrub_text

PY_SUFFIXES = frozenset({".py", ".pyi", ".pyw"})


class _TextHandler:
    name = "text"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "text"

    def audit(self, blob: Blob) -> list[Slip]:
        text = _decode(blob.data)
        slips: list[Slip] = []
        if blob.path.suffix in PY_SUFFIXES:
            slips.extend(tokens.collect(text))
        slips.extend(unicode.probe(text))
        slips.extend(signatures.match(text))
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        text, codec = _decode_codec(blob.data)
        pythonic = blob.path.suffix in PY_SUFFIXES
        cleaned, labels = scrub_text(text, pythonic, edits)
        if cleaned == text:
            return blob.data, labels
        return cleaned.encode(codec), labels


HANDLER: Handler = _TextHandler()


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _decode_codec(data: bytes) -> tuple[str, str]:
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"
