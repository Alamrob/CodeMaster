from __future__ import annotations

import re
from dataclasses import dataclass

from codemaster.catalog import REGISTRY
from codemaster.report import Grade, Slip

_RANKS = {"authorship": Grade.DANGER, "model": Grade.SIGNAL}


@dataclass(frozen=True)
class Fingerprint:
    kind: str
    rx: re.Pattern[str]
    rank: Grade
    group: str = ""


def _build() -> tuple[Fingerprint, ...]:
    rules: list[Fingerprint] = []

    def add(kind: str, rank: Grade, patterns: list[str]) -> None:
        for raw in patterns:
            rules.append(Fingerprint(kind, re.compile(raw, re.IGNORECASE), rank))

    for kind, patterns in REGISTRY.phrases.items():
        rank = _RANKS.get(kind, Grade.SIGNAL)
        add(kind, rank, list(patterns))
    for model in REGISTRY.models:
        rules.append(Fingerprint("model", model.compile(), Grade.SIGNAL, model.group))
    return tuple(rules)


REGISTRY_RULES = _build()


def match(source: str) -> list[Slip]:
    accepted: list[tuple[int, int, Slip]] = []
    for fp in REGISTRY_RULES:
        for found in fp.rx.finditer(source):
            slip = Slip(
                source.count("\n", 0, found.start()) + 1,
                1,
                fp.kind,
                found.group(0)[:48],
                fp.rank,
                fp.group,
            )
            contained = any(
                head <= found.start() and found.end() <= tail
                for head, tail, _ in accepted
            )
            if contained:
                continue
            accepted.append((found.start(), found.end(), slip))
    return [slip for _, _, slip in accepted]
