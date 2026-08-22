from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from codemaster import portal
from codemaster.catalog import REGISTRY
from codemaster.config import load as load_config
from codemaster.config import save as save_config
from codemaster.fsutil import Scope, list_files_all
from codemaster.report import (
    Grade,
    Ledger,
    render_html,
    render_human,
    render_json,
    render_markdown,
)
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


def _filter_ledger(ledger: Ledger, ns: argparse.Namespace) -> Ledger:
    groups = getattr(ns, "group", None)
    if groups:
        wanted = frozenset(g.strip().lower() for g in groups.split(",") if g.strip())
        ledger = ledger.filter_groups(wanted)
    kinds = getattr(ns, "kind", None)
    if kinds:
        wanted = frozenset(k.strip().lower() for k in kinds.split(",") if k.strip())
        ledger = ledger.filter_kinds(wanted)
    return ledger


def _run_scan(ns: argparse.Namespace) -> int:
    ledger = _filter_ledger(portal.tour(_paths(ns), _scope(ns)), ns)
    print(render_json(ledger) if ns.json else render_human(ledger))
    return 0


def _run_report(ns: argparse.Namespace) -> int:
    ledger = _filter_ledger(portal.tour(_paths(ns), _scope(ns)), ns)
    if ns.format == "json":
        body = render_json(ledger)
    elif ns.format == "md":
        body = render_markdown(ledger)
    elif ns.format == "html":
        body = render_html(ledger)
    else:
        body = render_human(ledger)
    if ns.output:
        ns.output.write_text(body, encoding="utf-8")
        print(f"reporte escrito en {ns.output}")
    else:
        print(body)
    return 0


def _run_config(ns: argparse.Namespace) -> int:
    if ns.show:
        config = load_config()
        for key, value in sorted(vars(config).items()):
            print(f"{key}={value}")
        return 0
    current = load_config()
    updates: dict[str, object] = {}
    if ns.workers is not None:
        updates["workers"] = ns.workers
    if ns.backup is not None:
        updates["backup"] = ns.backup
    if ns.glyphs is not None:
        updates["glyphs"] = ns.glyphs
    if ns.no_meta:
        updates["meta"] = False
    if not updates:
        print("sin cambios")
        return 0
    for key, value in updates.items():
        setattr(current, key, value)
    target = save_config(current)
    print(f"config guardada en {target}")
    return 0


def _run_catalog(ns: argparse.Namespace) -> int:
    group = ns.group
    by_group: dict[str, list[str]] = {}
    for model in REGISTRY.models:
        by_group.setdefault(model.group, []).append(model.name)
    print("== Grupos de huellas ==")
    for gname, desc in sorted(REGISTRY.groups.items()):
        print(f"  {gname:<8} {desc}")
    print()
    print("== Modelos registrados ==")
    for gname in sorted(by_group):
        if group and gname != group:
            continue
        names = ", ".join(sorted(by_group[gname]))
        print(f"  [{gname}] {names}")
    print()
    print(f"== Frases por categoria ==  {len(REGISTRY.phrases)} categorias")
    for kind, phrases in sorted(REGISTRY.phrases.items()):
        print(f"  {kind}: {len(phrases)} patrones")
    print(f"== Agentes C2PA ==  {len(REGISTRY.agents)} mapeos")
    print(f"== Vendors ==  {len(REGISTRY.vendors)} organizaciones")
    return 0


def _run_check(ns: argparse.Namespace) -> int:
    ledger = _filter_ledger(portal.tour(_paths(ns), _scope(ns)), ns)
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
    rows: list[tuple[Path, str, str, int, str, float]] = []
    for root in _paths(ns):
        for path in list_files_all(root, scope):
            blob = portal.blob_of(path, scope)
            if blob is None:
                continue
            sheet = portal.scan_one(path, scope)
            names = ", ".join(handler.name for handler in portal.handlers_for(blob))
            worst = max((mark.rank for mark in sheet.marks), default=Grade.HUSH)
            rows.append(
                (
                    path,
                    blob.kind,
                    names,
                    len(sheet.marks),
                    worst.name.lower(),
                    sheet.score(),
                )
            )
    if ns.json:
        import json

        payload = [
            {
                "path": str(path),
                "kind": kind,
                "handlers": names,
                "marks": count,
                "worst": worst,
                "score": score,
            }
            for path, kind, names, count, worst, score in rows
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for path, kind, names, count, worst_name, score in rows:
        print(
            f"{path}: kind={kind} handlers=[{names}] marks={count} worst={worst_name} score={score:.2f}"
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
    scan.add_argument("--group", help="filter by group(s): llm,image,video,audio,code")
    scan.add_argument("--kind", help="filter by mark kind(s): model,c2pa,exif,...")
    scan.set_defaults(handler=_run_scan)

    report = sub.add_parser("report", help="export analysis report")
    report.add_argument("paths", nargs="*", default=["."])
    report.add_argument(
        "--format", choices=["human", "md", "html", "json"], default="human"
    )
    report.add_argument("-o", "--output", type=Path)
    report.add_argument("--suffix", action="append")
    report.add_argument("--exclude", action="append")
    report.add_argument(
        "--group", help="filter by group(s): llm,image,video,audio,code"
    )
    report.add_argument("--kind", help="filter by mark kind(s): model,c2pa,exif,...")
    report.set_defaults(handler=_run_report)

    config_cmd = sub.add_parser("config", help="read or update persistent config")
    config_cmd.add_argument("--show", action="store_true", help="print current config")
    config_cmd.add_argument("--workers", type=int, help="parallel scan workers")
    config_cmd.add_argument("--backup", type=bool, help="default backup .bak")
    config_cmd.add_argument(
        "--glyphs", type=bool, help="default clean invisible glyphs"
    )
    config_cmd.add_argument(
        "--no-meta", action="store_true", help="skip metadata by default"
    )
    config_cmd.set_defaults(handler=_run_config)

    catalog_cmd = sub.add_parser("catalog", help="list registered AI marks and models")
    catalog_cmd.add_argument(
        "--group",
        choices=["llm", "image", "video", "audio", "code"],
        help="filter models by group",
    )
    catalog_cmd.set_defaults(handler=_run_catalog)

    check = sub.add_parser("check", help="CI gate")
    check.add_argument("paths", nargs="*", default=["."])
    check.add_argument("--json", action="store_true")
    check.add_argument("--strict", action="store_true")
    check.add_argument("--suffix", action="append")
    check.add_argument("--exclude", action="append")
    check.add_argument("--group", help="filter by group(s): llm,image,video,audio,code")
    check.add_argument("--kind", help="filter by mark kind(s): model,c2pa,exif,...")
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
