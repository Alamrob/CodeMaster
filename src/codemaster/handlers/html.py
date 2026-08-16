from __future__ import annotations

import re

from codemaster import signatures, unicode
from codemaster.handlers.base import Blob, Handler, line_of
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]*>")
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_MARKERS = ("generator", "author", "copyright", "content-type")
_WASH_META_RE = re.compile(
    r"<meta\b[^>]*(?:\b(?:generator|author)\b)[^>]*>", re.IGNORECASE
)


class _HtmlHandler:
    name = "html"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "html"

    def audit(self, blob: Blob) -> list[Slip]:
        text = _decode(blob.data)
        slips: list[Slip] = []
        for match in _COMMENT_RE.finditer(text):
            slips.append(
                Slip(
                    line_of(text, match.start()),
                    1,
                    "comment",
                    match.group(0)[:40],
                    Grade.DANGER,
                )
            )
        for match in _META_RE.finditer(text):
            if any(marker in match.group(0).lower() for marker in _META_MARKERS):
                slips.append(
                    Slip(
                        line_of(text, match.start()),
                        1,
                        "metatag",
                        match.group(0)[:48],
                        Grade.SIGNAL,
                    )
                )
        body = _TAG_RE.sub(" ", text)
        slips.extend(signatures.match(body))
        slips.extend(unicode.probe(text))
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        text, codec = _decode_codec(blob.data)
        cleaned = _COMMENT_RE.sub("", text)
        labels: list[str] = ["html-comments"]
        if edits.glyphs:
            cleaned = unicode.flush(cleaned)
            labels.append("glyphs")
        if edits.meta:
            cleaned = _WASH_META_RE.sub("", cleaned)
            labels.append("meta")
        if cleaned == text:
            return blob.data, labels
        return cleaned.encode(codec), labels


HANDLER: Handler = _HtmlHandler()


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
