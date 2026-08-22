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
    group: str = ""


@dataclass(frozen=True)
class Mark:
    path: Path
    line: int
    col: int
    kind: str
    note: str
    rank: Grade
    group: str = ""


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

    def evidence(self) -> str:
        """Classify the combined-evidence strength of the marks.

        ``none`` when there are no marks; ``weak`` for isolated mentions;
        ``moderate`` when several signals or groups appear; ``strong`` when a
        firm (dangerous) signal is corroborated by additional evidence.
        """
        if not self.marks:
            return "none"
        danger = any(mark.rank is Grade.DANGER for mark in self.marks)
        groups = {mark.group for mark in self.marks if mark.group}
        signals = sum(1 for mark in self.marks if mark.rank is not Grade.HUSH)
        if danger and signals >= 2:
            return "strong"
        if danger:
            return "moderate"
        if signals >= 3 or len(groups) >= 2:
            return "moderate"
        return "weak"


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

    def group_totals(self) -> dict[str, int]:
        """Count marks by catalog group (llm/image/video/audio/code/...)."""
        counts: dict[str, int] = {}
        for sheet in self.sheets:
            for mark in sheet.marks:
                group = mark.group or "other"
                counts[group] = counts.get(group, 0) + 1
        return counts

    def filter_groups(self, groups: frozenset[str]) -> Ledger:
        """Keep only marks whose group is in ``groups``; drop empty sheets."""
        kept: list[FileSheet] = []
        for sheet in self.sheets:
            marks = [m for m in sheet.marks if (m.group or "other") in groups]
            if marks:
                kept.append(FileSheet(sheet.path, marks))
        return Ledger(kept)

    def filter_kinds(self, kinds: frozenset[str]) -> Ledger:
        """Keep only marks whose kind is in ``kinds``; drop empty sheets."""
        kept: list[FileSheet] = []
        for sheet in self.sheets:
            marks = [m for m in sheet.marks if m.kind in kinds]
            if marks:
                kept.append(FileSheet(sheet.path, marks))
        return Ledger(kept)

    def filter_evidence(self, levels: frozenset[str]) -> Ledger:
        """Keep only files whose evidence level is in ``levels``."""
        kept: list[FileSheet] = []
        for sheet in self.sheets:
            if sheet.marks and sheet.evidence() in levels:
                kept.append(sheet)
        return Ledger(kept)


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
        "groups": ledger.group_totals(),
        "files": [
            {
                "path": str(sheet.path),
                "score": sheet.score(),
                "evidence": sheet.evidence(),
                "marks": [
                    {
                        "line": mark.line,
                        "col": mark.col,
                        "kind": mark.kind,
                        "note": mark.note,
                        "rank": mark.rank.name.lower(),
                        "group": mark.group,
                    }
                    for mark in sheet.marks
                ],
            }
            for sheet in ledger.sheets
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_markdown(ledger: Ledger) -> str:
    lines = ["# Reporte de huellas AI", ""]
    lines.append(f"- Verdicto: **{_verdict_name(ledger.worst())}**")
    totals = ledger.totals()
    lines.append(
        "- Totales: "
        + (", ".join(f"{k}={v}" for k, v in sorted(totals.items())) or "ninguna")
    )
    groups = ledger.group_totals()
    if groups:
        lines.append(
            "- Grupos: " + ", ".join(f"{k}={v}" for k, v in sorted(groups.items()))
        )
    files = [sheet for sheet in ledger.sheets if sheet.marks]
    lines.append(f"- Archivos con senales: {len(files)} / {len(ledger.sheets)}")
    lines.append("")
    for sheet in files:
        lines.append(f"## {sheet.path}")
        lines.append(f"- score: {sheet.score():.2f}  evidencia: {sheet.evidence()}")
        for mark in sheet.marks:
            group = f" [{mark.group}]" if mark.group else ""
            lines.append(
                f"- [{mark.rank.name.lower()}]{group} `{mark.kind}` "
                f"({mark.line}:{mark.col}) {mark.note}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(ledger: Ledger) -> str:
    totals = ledger.totals()
    badges = " ".join(
        f'<span class="badge">{k}: {v}</span>' for k, v in sorted(totals.items())
    )
    rows: list[str] = []
    for sheet in ledger.sheets:
        if not sheet.marks:
            continue
        marks = "".join(_html_mark(mark) for mark in sheet.marks)
        rows.append(
            f'<tr><td class="path">{_esc(str(sheet.path))}</td>'
            f"<td>{sheet.score():.2f}</td>"
            f"<td>{len(sheet.marks)}</td>"
            f'<td><ul class="marks">{marks}</ul></td></tr>'
        )
    body_rows = "".join(rows) or '<tr><td colspan="4">Sin senales</td></tr>'
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Reporte CodeMaster</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}
 h1{{border-bottom:2px solid #eee;padding-bottom:.5rem}}
 .badge{{background:#f1f3f5;border-radius:12px;padding:2px 10px;margin-right:6px}}
 table{{border-collapse:collapse;width:100%;margin-top:1rem}}
 th,td{{border:1px solid #e5e7eb;padding:8px;text-align:left;vertical-align:top}}
 th{{background:#f9fafb}}
 .marks{{margin:0;padding-left:1.1rem}}
 .danger{{color:#b91c1c}}
 .signal{{color:#b45309}}
 .hush{{color:#6b7280}}
</style></head><body>
<h1>Reporte de huellas AI</h1>
<p>Verdicto: <b>{_verdict_name(ledger.worst())}</b></p>
<p>{badges}</p>
<table><thead><tr><th>Archivo</th><th>Score</th><th>Marcas</th><th>Detalle</th></tr></thead>
<tbody>{body_rows}</tbody></table>
</body></html>"""


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html_mark(mark: Mark) -> str:
    badge = f'<span class="badge">{_esc(mark.group)}</span>' if mark.group else ""
    return (
        f'<li class="{mark.rank.name.lower()}"><b>{_esc(mark.kind)}</b> '
        f"{badge}({mark.line}:{mark.col}) {_esc(mark.note)}</li>"
    )


def _verdict_name(grade: Grade) -> str:
    if grade >= Grade.DANGER:
        return "DANGER"
    if grade >= Grade.SIGNAL:
        return "SIGNAL"
    return "clean"
