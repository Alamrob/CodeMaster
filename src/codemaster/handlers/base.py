from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codemaster.report import Slip
from codemaster.scrubber import Edits


@dataclass(frozen=True)
class Blob:
    path: Path
    data: bytes
    kind: str


class Handler(Protocol):
    name: str

    def probe(self, blob: Blob) -> bool: ...

    def audit(self, blob: Blob) -> list[Slip]: ...

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]: ...


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
