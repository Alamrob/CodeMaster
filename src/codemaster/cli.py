from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from codemaster import portal
from codemaster.fsutil import Scope, list_files_all
from codemaster.report import Grade, render_human, render_json
from codemaster.scrubber import Edits


def _scope(ns: argparse.Namespace) -> Scope:
    scope = Scope()
    if ns.suffix:
        scope = Scope(frozenset(ns.suffix))
    if ns.exclude:
        scope = Scope(scope.suffixes, scope.skip | frozenset(ns.exclude))
    return scope


def _paths(ns: argparse.Namespace) -> list[Path]:
    return [Path(item) for item in ns.paths]


def _run_scan(ns: argparse.Namespace) -> int:
    ledger = portal.tour(_paths(ns), _scope(ns))
    print(render_json(ledger) if ns.json else render_human(ledger))
    return 0


def _run_check(ns: argparse.Namespace) -> int:
    ledger = portal.tour(_paths(ns), _scope(ns))
    threshold = Grade.SIGNAL if ns.strict else Grade.DANGER
    print(render_json(ledger) if ns.json else render_human(ledger))
    return 1 if ledger.worst() >= threshold else 0


def _run_scrub(ns: argparse.Namespace) -> int:
    scope = _scope(ns)
    edits = Edits(glyphs=ns.fix_unicode, meta=not ns.keep_meta)
    altered = 0
    applied = 0
    for root in _paths(ns):
        for path in list_files_all(root, scope):
            result = portal.wash_path(
                path, edits, scope, backup=ns.backup, apply_write=ns.apply
            )
            if not result.altered:
                continue
            altered += 1
            if result.written:
                applied += 1
            state = "rewritten" if result.written else "would rewrite"
            suffix = f" backup={result.backup.name}" if result.backup else ""
            print(f"{path}: {state} [{', '.join(result.labels)}]{suffix}")
    print(f"scrub: {altered} files touched, {applied} applied")
    return 0


def _run_identify(ns: argparse.Namespace) -> int:
    scope = _scope(ns)
    rows: list[tuple[Path, str, str, int, str]] = []
    for root in _paths(ns):
        for path in list_files_all(root, scope):
            blob = portal.blob_of(path, scope)
            if blob is None:
                continue
            slips = portal.audit(blob)
            names = ", ".join(handler.name for handler in portal.handlers_for(blob))
            worst = max((slip.rank for slip in slips), default=Grade.HUSH)
            rows.append((path, blob.kind, names, len(slips), worst.name.lower()))
    if ns.json:
        import json

        payload = [
            {
                "path": str(path),
                "kind": kind,
                "handlers": names,
                "marks": count,
                "worst": worst,
            }
            for path, kind, names, count, worst in rows
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for path, kind, names, count, worst_name in rows:
        print(
            f"{path}: kind={kind} handlers=[{names}] marks={count} worst={worst_name}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemaster")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="inventory findings")
    scan.add_argument("paths", nargs="*", default=["."])
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--suffix", action="append")
    scan.add_argument("--exclude", action="append")
    scan.set_defaults(handler=_run_scan)

    check = sub.add_parser("check", help="CI gate")
    check.add_argument("paths", nargs="*", default=["."])
    check.add_argument("--json", action="store_true")
    check.add_argument("--strict", action="store_true")
    check.add_argument("--suffix", action="append")
    check.add_argument("--exclude", action="append")
    check.set_defaults(handler=_run_check)

    scrub = sub.add_parser("scrub", help="sanitize sources")
    scrub.add_argument("paths", nargs="*", default=["."])
    scrub.add_argument("--apply", action="store_true")
    scrub.add_argument("--backup", action="store_true")
    scrub.add_argument("--fix-unicode", action="store_true")
    scrub.add_argument("--keep-meta", action="store_true")
    scrub.add_argument("--suffix", action="append")
    scrub.add_argument("--exclude", action="append")
    scrub.set_defaults(handler=_run_scrub)

    identify = sub.add_parser("identify", help="classify and list provenance signals")
    identify.add_argument("paths", nargs="*", default=["."])
    identify.add_argument("--json", action="store_true")
    identify.add_argument("--suffix", action="append")
    identify.add_argument("--exclude", action="append")
    identify.set_defaults(handler=_run_identify)

    return parser


def _reconfigure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            cast(Any, stream).reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _reconfigure_stdout()
    parser = build_parser()
    ns = parser.parse_args(argv)
    handler = cast(Callable[[argparse.Namespace], int], ns.handler)
    return handler(ns)


def entry() -> int:
    return main(sys.argv[1:])
