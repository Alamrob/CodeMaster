from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from codemaster.scrubber import Edits


@dataclass
class Config:
    workers: int = 0
    backup: bool = True
    comments: bool = True
    docstrings: bool = True
    meta: bool = True
    glyphs: bool = False
    last_path: str = ""

    def edits(self) -> Edits:
        return Edits(
            comments=self.comments,
            docstrings=self.docstrings,
            glyphs=self.glyphs,
            meta=self.meta,
        )


def default_path() -> Path:
    base = os.environ.get("CODEMASTER_CONFIG", "")
    if base:
        return Path(base)
    return Path.home() / ".codemaster.json"


def load(path: Path | None = None) -> Config:
    config = Config()
    source = path if path is not None else default_path()
    if not source.exists():
        return config
    try:
        data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config
    known = {f.name: f for f in fields(Config)}
    for key, value in data.items():
        field = known.get(key)
        if field is None or not isinstance(value, (int, float, str, bool)):
            continue
        type_name = getattr(field.type, "__name__", str(field.type))
        if type_name == "bool" and not isinstance(value, bool):
            continue
        if type_name == "int" and not isinstance(value, int):
            continue
        setattr(config, key, value)
    return config


def save(config: Config, path: Path | None = None) -> Path:
    target = path if path is not None else default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
