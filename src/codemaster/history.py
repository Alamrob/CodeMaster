from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codemaster.scrubber import WashResult


def history_dir() -> Path:
    base = os.environ.get("CODEMASTER_HOME", "")
    if base:
        return Path(base)
    return Path.home() / ".codemaster"


def history_file() -> Path:
    return history_dir() / "history.jsonl"


def record(results: list[WashResult], source: str, backup: bool) -> Path:
    """Append an idempotent JSONL entry per washed file.

    Files that were not altered or written are skipped. Returns the history
    file path so callers can report where the record landed.
    """
    target = history_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    entries: list[dict[str, Any]] = []
    for result in results:
        if not result.written:
            continue
        entry = {
            "ts": stamp,
            "source": source,
            "backup": backup,
            "path": str(result.path),
            "labels": sorted(result.labels),
            "backup_path": str(result.backup) if result.backup is not None else None,
        }
        entries.append(entry)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return target


def load(max_entries: int = 200) -> list[dict[str, Any]]:
    target = history_file()
    if not target.exists():
        return []
    lines: list[str] = []
    try:
        with target.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines[-max_entries:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries
