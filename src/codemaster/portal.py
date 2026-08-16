from __future__ import annotations

import io
from pathlib import Path

from codemaster.fsutil import Scope, walk_all
from codemaster.handlers import _deps, chain
from codemaster.handlers.base import Blob, Handler
from codemaster.kind import classify
from codemaster.report import FileSheet, Grade, Ledger, Mark, Slip
from codemaster.scrubber import Edits, WashResult


def blob_of(path: Path, scope: Scope) -> Blob | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return Blob(path, data, classify(path, data, scope.suffixes))


def handlers_for(blob: Blob) -> list[Handler]:
    return chain(blob)


def audit(blob: Blob) -> list[Slip]:
    slips: list[Slip] = []
    for handler in chain(blob):
        try:
            slips.extend(handler.audit(blob))
        except Exception:
            slips.append(Slip(1, 1, "handler", handler.name, Grade.HUSH))
    return slips


def scan_one(path: Path, scope: Scope) -> FileSheet:
    blob = blob_of(path, scope)
    if blob is None:
        return FileSheet(path, [Mark(path, 1, 1, "access", "unreadable", Grade.HUSH)])
    marks = [
        Mark(path, slip.line, slip.col, slip.kind, slip.note, slip.rank)
        for slip in audit(blob)
    ]
    marks.sort(key=lambda mark: (mark.line, mark.col))
    return FileSheet(path, marks)


def tour(roots: list[Path], scope: Scope) -> Ledger:
    sheets = [
        scan_one(path, scope) for root in roots for path in _walk_all_files(root, scope)
    ]
    return Ledger(sheets)


def wash_path(
    path: Path,
    edits: Edits,
    scope: Scope,
    backup: bool = False,
    apply_write: bool = False,
) -> WashResult:
    blob = blob_of(path, scope)
    if blob is None:
        return WashResult(path, False, [])
    original = blob.data
    current = blob
    labels: list[str] = []
    for handler in chain(current):
        try:
            out, found = handler.wash(current, edits)
        except Exception:
            continue
        current = Blob(path, out, current.kind)
        labels.extend(found)
    altered = current.data != original
    if altered and current.kind == "image":
        restored = _verify_wash_image(original, current.data)
        if restored is not None:
            current = Blob(path, restored, current.kind)
            labels = []
            altered = False
    if not apply_write:
        return WashResult(path, altered, sorted(set(labels)))
    saved: Path | None = None
    if backup and altered:
        saved = path.with_name(path.name + ".bak")
        if not saved.exists():
            saved.write_bytes(original)
    if altered:
        path.write_bytes(current.data)
    return WashResult(path, altered, sorted(set(labels)), saved, altered)


def _walk_all_files(root: Path, scope: Scope) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(walk_all(root, scope))


def _verify_wash_image(pre: bytes, post: bytes) -> bytes | None:
    """Roll back a wash that broke a decodable image.

    Returns ``pre`` (the original bytes) when pillow can decode ``pre`` but no
    longer decodes ``post``, and ``None`` otherwise. Files that never decoded
    (truncated, synthetic, or unsupported) are never gated, so structural
    washes of non-decodable input are never reverted.
    """
    if not _deps.pillow_ok():
        return None
    image = _deps.load("PIL.Image")

    def decodes(data: bytes) -> bool:
        try:
            with image.open(io.BytesIO(data)) as opened:
                opened.verify()
        except Exception:
            return False
        return True

    if not decodes(pre):
        return None
    if decodes(post):
        return None
    return pre
