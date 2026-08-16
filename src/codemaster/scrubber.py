from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path

from codemaster.fsutil import decode
from codemaster.unicode import stealth_ranges

Span = tuple[int, int, int, int]


@dataclass(frozen=True)
class Edits:
    comments: bool = True
    docstrings: bool = True
    glyphs: bool = False
    meta: bool = True


@dataclass
class WashResult:
    path: Path
    altered: bool
    labels: list[str]
    backup: Path | None = None
    written: bool = False


def _offsets(text: str) -> list[int]:
    starts = [0]
    cursor = text.find("\n")
    while cursor != -1:
        starts.append(cursor + 1)
        cursor = text.find("\n", cursor + 1)
    return starts


def _cut(
    text: str,
    line_spans: list[Span],
    char_spans: list[tuple[int, int]],
) -> str:
    starts = _offsets(text)
    cuts: list[tuple[int, int]] = [
        (starts[line0] + col0, starts[line1] + col1)
        for line0, col0, line1, col1 in line_spans
    ]
    cuts.extend(char_spans)
    cuts.sort()
    merged: list[tuple[int, int]] = []
    for begin, end in cuts:
        if begin >= end:
            continue
        if merged and begin <= merged[-1][1]:
            prev = merged[-1]
            merged[-1] = (prev[0], max(prev[1], end))
        else:
            merged.append((begin, end))
    parts: list[str] = []
    cursor = 0
    for begin, end in merged:
        parts.append(text[cursor:begin])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _comment_spans(source: str) -> list[Span]:
    spans: list[Span] = []
    lines = source.split("\n")
    try:
        reader = io.StringIO(source)
        for token in tokenize.generate_tokens(reader.readline):
            if token.type != tokenize.COMMENT:
                continue
            line0, col0 = token.start
            line1, col1 = token.end
            column = col0
            pad = 0
            while column - 1 - pad >= 0 and lines[line0 - 1][column - 1 - pad] in " \t":
                pad += 1
            spans.append((line0 - 1, col0 - pad, line1 - 1, col1))
    except (tokenize.TokenError, IndentationError):
        pass
    return spans


def _docstring_spans(source: str) -> list[Span]:
    spans: list[Span] = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return spans
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        value = first.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        spans.append(
            (
                first.lineno - 1,
                first.col_offset,
                first.end_lineno - 1
                if first.end_lineno is not None
                else first.lineno - 1,
                first.end_col_offset
                if first.end_col_offset is not None
                else first.col_offset,
            )
        )
    return spans


def scrub_text(source: str, pythonic: bool, edits: Edits) -> tuple[str, list[str]]:
    labels: list[str] = []
    line_spans: list[Span] = []
    char_spans: list[tuple[int, int]] = []
    if pythonic and edits.docstrings:
        line_spans.extend(_docstring_spans(source))
        labels.append("docstrings")
    if pythonic and edits.comments:
        line_spans.extend(_comment_spans(source))
        labels.append("comments")
    if edits.glyphs:
        char_spans.extend(stealth_ranges(source))
        labels.append("glyphs")
    cleaned = _cut(source, line_spans, char_spans)
    if cleaned != source:
        cleaned = "\n".join(line.rstrip() for line in cleaned.split("\n"))
    labels.sort()
    return cleaned, labels


def wash_file(
    path: Path,
    edits: Edits,
    backup: bool = False,
    apply_write: bool = False,
) -> WashResult:
    data = path.read_bytes()
    text, codec = decode(data)
    pythonic = path.suffix in {".py", ".pyi", ".pyw"}
    cleaned, labels = scrub_text(text, pythonic, edits)
    altered = cleaned != text
    if not apply_write:
        return WashResult(path, altered, labels)
    blob: Path | None = None
    if backup and altered:
        blob = path.with_name(path.name + ".bak")
        if not blob.exists():
            blob.write_bytes(data)
    if altered:
        path.write_bytes(cleaned.encode(codec))
    return WashResult(path, altered, labels, blob, altered)
