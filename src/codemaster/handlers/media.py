from __future__ import annotations

from codemaster import signatures
from codemaster.handlers.base import Blob, Handler
from codemaster.handlers.image_meta import (
    _AI_TOOL_TERMS,
    _bmff_audit,
    _bmff_wash,
    _c2pa_slips,
    _trail_scan,
)
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits

_ID3_FRAMES = (b"TIT2", b"TPE1", b"TALB", b"COMM", b"TXXX", b"TOOL")
_MODEL_MARKERS = (b"gguf", b"llama", b"mistral", b"deepseek", b"chatglm", b"qwen")


def _strings(data: bytes) -> list[str]:
    runs: list[str] = []
    current: list[int] = []
    for byte in data:
        if byte in (9, 10, 13) or 32 <= byte <= 126:
            current.append(byte)
        else:
            if len(current) >= 4:
                runs.append(bytes(current).decode("latin-1"))
            current = []
    if len(current) >= 4:
        runs.append(bytes(current).decode("latin-1"))
    return runs


def _tool_markers(data: bytes) -> list[tuple[str, Grade]]:
    lowered = data.lower()
    hits: list[tuple[str, Grade]] = []
    for term in _AI_TOOL_TERMS:
        if term.encode() in lowered:
            hits.append((term, Grade.SIGNAL))
    for marker in _MODEL_MARKERS:
        if marker in lowered:
            hits.append((marker.decode(), Grade.SIGNAL))
    return hits


class _MediaHandler:
    name = "media"

    def probe(self, blob: Blob) -> bool:
        return blob.kind in ("audio", "video", "model")

    def audit(self, blob: Blob) -> list[Slip]:
        data = blob.data
        slips: list[Slip] = []
        if blob.kind == "video":
            slips.extend(_bmff_audit(data))
            slips.extend(_trail_scan(data))
            slips.extend(_c2pa_slips(data))
        for marker, rank in _tool_markers(data):
            index = data.lower().find(marker.encode())
            if index != -1:
                slips.append(Slip(1, index + 1, "marker", marker[:48], rank))
        for text in _strings(data):
            slips.extend(signatures.match(text))
        return _dedupe(slips)

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        if blob.kind == "video":
            return _bmff_wash(blob.data)
        return blob.data, []


HANDLER: Handler = _MediaHandler()


def _dedupe(slips: list[Slip]) -> list[Slip]:
    seen: set[tuple[int, str]] = set()
    out: list[Slip] = []
    for slip in slips:
        key = (slip.line, slip.kind)
        if key in seen:
            continue
        seen.add(key)
        out.append(slip)
    return out
