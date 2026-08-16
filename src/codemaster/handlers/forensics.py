from __future__ import annotations

from codemaster import signatures
from codemaster.handlers.base import Blob, Handler
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits

_RAW_MARKERS = (
    b"c2pa",
    b"jumbf",
    b"synthid",
    b"ContentCredentials",
    b"generated-by",
    b"Author",
    b"Creator",
    b"Producer",
)


class _ForensicHandler:
    name = "forensic"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "binary"

    def audit(self, blob: Blob) -> list[Slip]:
        data = blob.data
        slips: list[Slip] = []
        slips.extend(signatures.match(_extract_strings(data)))
        for marker in _RAW_MARKERS:
            index = data.find(marker)
            if index != -1:
                slips.append(
                    Slip(
                        1,
                        index + 1,
                        "forensic",
                        marker.decode(errors="replace"),
                        Grade.SIGNAL,
                    )
                )
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        return blob.data, []


HANDLER: Handler = _ForensicHandler()


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
