from __future__ import annotations

import ast
import io
import tokenize

from codemaster.report import Grade, Slip


def _docstring_slips(tree: ast.AST) -> list[Slip]:
    found: list[Slip] = []
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
        start = getattr(value, "lineno", None)
        if start is None:
            continue
        sample = value.value.strip().replace("\n", " ")[:48]
        found.append(
            Slip(
                start,
                getattr(value, "col_offset", 0) + 1,
                "docstring",
                sample,
                Grade.DANGER,
            )
        )
    return found


def _comment_slips(source: str) -> list[Slip]:
    found: list[Slip] = []
    try:
        reader = io.StringIO(source)
        for token in tokenize.generate_tokens(reader.readline):
            if token.type != tokenize.COMMENT:
                continue
            line, col = token.start
            found.append(
                Slip(line, col + 1, "comment", token.string[:48], Grade.DANGER)
            )
    except (tokenize.TokenError, IndentationError, UnicodeDecodeError):
        pass
    return found


def collect(source: str) -> list[Slip]:
    slips = _comment_slips(source)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        slips.append(Slip(1, 1, "malformed", "ast unreachable", Grade.HUSH))
        return slips
    return slips + _docstring_slips(tree)
