from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".pyw",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".md",
        ".rst",
        ".txt",
        ".html",
        ".css",
        ".scss",
        ".sh",
        ".ps1",
        ".bat",
        ".sql",
        ".jsonl",
        ".mdx",
        ".log",
        ".epub",
        ".mp3",
        ".wav",
        ".flac",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".mp4",
        ".mov",
        ".m4v",
        ".mkv",
        ".webm",
        ".avi",
        ".gguf",
        ".onnx",
        ".safetensors",
    }
)

DEFAULT_SKIP = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        ".tox",
        ".nox",
        "build",
        "dist",
        ".idea",
        ".vscode",
    }
)


@dataclass(frozen=True)
class Scope:
    suffixes: frozenset[str] = DEFAULT_SUFFIXES
    skip: frozenset[str] = DEFAULT_SKIP


def walk_files(root: Path, scope: Scope) -> Iterator[Path]:
    for base, dirs, names in os.walk(root):
        dirs[:] = [dir_name for dir_name in dirs if dir_name not in scope.skip]
        for name in names:
            if _ignored_name(name) or name in scope.skip:
                continue
            path = Path(base) / name
            if path.suffix in scope.suffixes:
                yield path


def list_files(root: Path, scope: Scope) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix in scope.suffixes else []
    return sorted(walk_files(root, scope))


def walk_all(root: Path, scope: Scope) -> Iterator[Path]:
    for base, dirs, names in os.walk(root):
        dirs[:] = [dir_name for dir_name in dirs if dir_name not in scope.skip]
        for name in names:
            if _ignored_name(name) or name in scope.skip:
                continue
            yield Path(base) / name


def list_files_all(root: Path, scope: Scope) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(walk_all(root, scope))


def _ignored_name(name: str) -> bool:
    return name.endswith((".bak", ".orig", ".old")) or name.endswith("~")


def decode(data: bytes) -> tuple[str, str]:
    for codec in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(codec), codec
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1"), "latin-1"


def line_starts(text: str) -> list[int]:
    starts = [0]
    cursor = text.find("\n")
    while cursor != -1:
        starts.append(cursor + 1)
        cursor = text.find("\n", cursor + 1)
    return starts


def offset_line_col(
    text: str,
    offset: int,
    starts: list[int] | None = None,
) -> tuple[int, int]:
    if starts is None:
        starts = line_starts(text)
    low, high = 0, len(starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low + 1, offset - starts[low] + 1
