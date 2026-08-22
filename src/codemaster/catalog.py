from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CATALOG = Path(__file__).with_name("signatures.toml")


@dataclass(frozen=True)
class Model:
    name: str
    group: str
    patterns: tuple[str, ...]

    def compile(self) -> re.Pattern[str]:
        body = "|".join(self.patterns)
        return re.compile(f"\\b(?:{body})\\b", re.IGNORECASE)


@dataclass(frozen=True)
class Catalog:
    groups: dict[str, str]
    models: tuple[Model, ...]
    phrases: dict[str, tuple[str, ...]]
    agents: dict[str, str]
    vendors: dict[str, str]

    def model_named(self, name: str) -> Model | None:
        for model in self.models:
            if model.name == name:
                return model
        return None

    def resolve_agent(self, text: str) -> str | None:
        """Map a C2PA claim_generator / softwareAgent string to a model name."""
        lowered = text.lower()
        for token, name in self.agents.items():
            if token in lowered:
                return name
        return None


def load(path: Path | None = None) -> Catalog:
    source = path if path is not None else _CATALOG
    with source.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    groups = dict(data.get("groups", {}))
    models = tuple(
        Model(
            str(entry["name"]),
            str(entry.get("group", "llm")),
            tuple(str(p) for p in entry.get("patterns", ())),
        )
        for entry in data.get("models", [])
    )
    phrases = {
        str(key): tuple(str(p) for p in value)
        for key, value in data.get("phrases", {}).items()
    }
    agents = {str(k): str(v) for k, v in data.get("agents", {}).items()}
    vendors = {str(k): str(v) for k, v in data.get("vendors", {}).items()}
    return Catalog(groups, models, phrases, agents, vendors)


REGISTRY = load()
