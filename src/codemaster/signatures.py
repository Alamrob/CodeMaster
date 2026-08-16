from __future__ import annotations

import re
from dataclasses import dataclass

from codemaster.report import Grade, Slip


@dataclass(frozen=True)
class Fingerprint:
    kind: str
    rx: re.Pattern[str]
    rank: Grade


def _build() -> tuple[Fingerprint, ...]:
    rules: list[Fingerprint] = []

    def add(kind: str, rank: Grade, *patterns: str) -> None:
        for raw in patterns:
            rules.append(Fingerprint(kind, re.compile(raw, re.IGNORECASE), rank))

    add(
        "authorship",
        Grade.DANGER,
        r"\b(?:generated|created|written|authored|produced|built)\s+by\s+(?:claude|chatgpt|gpt-?\d?|openai|github\s+copilot|gemini|bard|llama|mistral|codex)",
        r"\b(?:made|developed)\s+with\s+(?:claude|chatgpt|openai|github\s+copilot|gemini|bard)",
        r"\bas\s+an\s+ai\s+(?:assistant|language\s+model|model)\b",
        r"\bai\s+(?:assistant|model)\s+generated\b",
    )
    add(
        "model",
        Grade.SIGNAL,
        r"\b(?:claude|chatgpt|gpt-4o|gpt-4|gpt-3\.5|codellama|gemini|mistral|llama-?\d?)\b",
    )
    add(
        "narration",
        Grade.SIGNAL,
        r"\bnote\s+that\b",
        r"\bplease\s+note\b",
        r"\bkeep\s+in\s+mind\b",
        r"\bin\s+conclusion\b",
        r"\bhope\s+this\s+helps\b",
        r"\bfeel\s+free\s+to\b",
        r"\blet'?s\s+dive\b",
        r"\bhere'?s\s+how\b",
        r"\bas\s+you\s+can\s+see\b",
        r"\bremember\s+to\b",
        r"\bdon'?t\s+forget\s+to\b",
        r"\bof\s+course\b",
        r"\bimportantly\b",
        r"\bas\s+always\b",
        r"\bhappy\s+to\s+help\b",
        r"\bany\s+questions\b",
        r"\bfor\s+your\s+convenience\b",
    )
    add(
        "fragment",
        Grade.SIGNAL,
        r"\brest\s+of\s+the\s+code\b",
        r"\bremaining\s+logic\b",
        r"\bremainder\s+of\s+the\b",
        r"\btruncated\s+for\s+brevity\b",
        r"\byour\s+code\s+here\b",
        r"\bsome\s+code\s+here\b",
        r"\blorem\s+ipsum\b",
    )
    return tuple(rules)


REGISTRY = _build()


def match(source: str) -> list[Slip]:
    accepted: list[tuple[int, int, Slip]] = []
    for fp in REGISTRY:
        for found in fp.rx.finditer(source):
            slip = Slip(
                source.count("\n", 0, found.start()) + 1,
                1,
                fp.kind,
                found.group(0)[:48],
                fp.rank,
            )
            contained = any(
                head <= found.start() and found.end() <= tail
                for head, tail, _ in accepted
            )
            if contained:
                continue
            accepted.append((found.start(), found.end(), slip))
    return [slip for _, _, slip in accepted]
