from __future__ import annotations

import contextlib
import io
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from codemaster.fsutil import Scope, walk_all
from codemaster.handlers import _deps, chain
from codemaster.handlers.base import Blob, Handler
from codemaster.kind import classify
from codemaster.report import FileSheet, Grade, Ledger, Mark, Slip
from codemaster.scrubber import Edits, WashResult

ProgressFn = Callable[[int, int], None]
CancelFn = Callable[[], bool]


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
        Mark(
            path,
            slip.line,
            slip.col,
            slip.kind,
            slip.note,
            slip.rank,
            slip.group,
        )
        for slip in audit(blob)
    ]
    marks.sort(key=lambda mark: (mark.line, mark.col))
    return FileSheet(path, marks)


def tour(roots: list[Path], scope: Scope) -> Ledger:
    sheets = [
        scan_one(path, scope) for root in roots for path in _walk_all_files(root, scope)
    ]
    return Ledger(sheets)


def tour_parallel(
    roots: list[Path],
    scope: Scope,
    workers: int = 0,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> Ledger:
    """Scan many files in parallel with optional progress/cancellation.

    ``progress(done, total)`` is invoked from the calling thread as each file
    completes. ``cancel()`` returning True stops scheduling new work early.
    """
    paths = [path for root in roots for path in _walk_all_files(root, scope)]
    total = len(paths)
    if total == 0:
        if progress is not None:
            progress(0, 0)
        return Ledger([])
    if workers <= 0:
        workers = max(1, min(32, (os.cpu_count() or 1) * 2))
    sheets: list[FileSheet | None] = [None] * total
    done = 0
    if cancel is not None and cancel():
        return Ledger([])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(scan_one, path, scope): index
            for index, path in enumerate(paths)
        }
        for future in as_completed(futures):
            if cancel is not None and cancel():
                for other in futures:
                    other.cancel()
                break
            index = futures[future]
            try:
                sheets[index] = future.result()
            except Exception:  # pragma: no cover - defensive
                sheets[index] = FileSheet(paths[index], [])
            done += 1
            if progress is not None:
                progress(done, total)
    return Ledger([sheet for sheet in sheets if sheet is not None])


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
        _atomic_write(path, current.data, original)
    return WashResult(path, altered, sorted(set(labels)), saved, altered)


def _atomic_write(path: Path, data: bytes, original: bytes) -> None:
    """Write ``data`` to ``path`` atomically, rolling back on failure.

    Writes to a temporary sibling file then renames over the target so the
    destination is never left half-written. If the rename fails, the original
    bytes are restored in place.
    """
    tmp = path.with_name(path.name + ".cmtmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        path.write_bytes(original)
        raise


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
