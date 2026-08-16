from __future__ import annotations

import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any


class Grade(IntEnum):
    HUSH = 0
    SIGNAL = 1
    DANGER = 2


@dataclass(frozen=True)
class Slip:
    line: int
    col: int
    kind: str
    note: str
    rank: Grade


@dataclass(frozen=True)
class Mark:
    path: Path
    line: int
    col: int
    kind: str
    note: str
    rank: Grade


@dataclass
class FileSheet:
    path: Path
    marks: list[Mark]

    def score(self) -> float:
        """Aggregate confidence that the file carries AI provenance.

        Each mark contributes a weight by rank (dangerous signals dominate);
        the sum is clamped to ``1.0``. ``0.0`` means no signals at all.
        """
        total = sum(_SCORE_WEIGHTS[mark.rank] for mark in self.marks)
        return min(1.0, total)


_SCORE_WEIGHTS = {Grade.HUSH: 0.0, Grade.SIGNAL: 0.2, Grade.DANGER: 0.6}


@dataclass
class Ledger:
    sheets: list[FileSheet]

    def worst(self) -> Grade:
        return max(
            (mark.rank for sheet in self.sheets for mark in sheet.marks),
            default=Grade.HUSH,
        )

    def totals(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for sheet in self.sheets:
            for mark in sheet.marks:
                counts[mark.kind] = counts.get(mark.kind, 0) + 1
        return counts


def sheet_render(sheet: FileSheet) -> str:
    rows = [
        f"{mark.path}:{mark.line}:{mark.col}  {mark.kind:<10} {mark.note}"
        for mark in sheet.marks
    ]
    return "\n".join(rows)


def render_human(ledger: Ledger) -> str:
    blocks = [sheet_render(sheet) for sheet in ledger.sheets if sheet.marks]
    totals = ledger.totals()
    head = ", ".join(f"{key}={value}" for key, value in sorted(totals.items()))
    worst = ledger.worst()
    verdict = (
        "DANGER"
        if worst >= Grade.DANGER
        else "SIGNAL"
        if worst >= Grade.SIGNAL
        else "clean"
    )
    return "\n".join(blocks) + f"\n---\ntotals: {head or 'none'}\nverdict: {verdict}"


def render_json(ledger: Ledger) -> str:
    payload: dict[str, Any] = {
        "worst": ledger.worst().name.lower(),
        "totals": ledger.totals(),
        "files": [
            {
                "path": str(sheet.path),
                "score": sheet.score(),
                "marks": [
                    {
                        "line": mark.line,
                        "col": mark.col,
                        "kind": mark.kind,
                        "note": mark.note,
                        "rank": mark.rank.name.lower(),
                    }
                    for mark in sheet.marks
                ],
            }
            for sheet in ledger.sheets
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
