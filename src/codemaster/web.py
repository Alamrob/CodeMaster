from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from codemaster import history, portal
from codemaster.config import Config
from codemaster.config import load as load_config
from codemaster.config import save as save_config
from codemaster.fsutil import Scope
from codemaster.report import Grade, render_html, render_json, render_markdown
from codemaster.scrubber import Edits

_HTML = Path(__file__).with_name("web_index.html")


def _scope_from(params: dict[str, list[str]]) -> Scope:
    scope = Scope()
    exclude = params.get("exclude")
    if exclude:
        scope = Scope(scope.suffixes, scope.skip | frozenset(exclude))
    return scope


def _sheet_payload(sheet: Any) -> dict[str, Any]:
    return {
        "path": str(sheet.path),
        "score": sheet.score(),
        "worst": max((m.rank for m in sheet.marks), default=Grade.HUSH).name.lower(),
        "groups": _group_counts(sheet),
        "marks": [
            {
                "line": m.line,
                "col": m.col,
                "kind": m.kind,
                "note": m.note,
                "rank": m.rank.name.lower(),
                "group": m.group,
            }
            for m in sheet.marks
        ],
    }


def _group_counts(sheet: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for mark in sheet.marks:
        group = mark.group or "other"
        counts[group] = counts.get(group, 0) + 1
    return counts


def _run_scan(
    roots: list[Path],
    scope: Scope,
    config: Config,
    emit: Callable[[dict[str, Any]], None],
) -> None:
    def progress(done: int, total: int) -> None:
        emit({"type": "progress", "done": done, "total": total})

    ledger = portal.tour_parallel(
        roots, scope, workers=config.workers, progress=progress
    )
    emit(
        {
            "type": "done",
            "totals": ledger.totals(),
            "worst": ledger.worst().name.lower(),
            "files": [_sheet_payload(sheet) for sheet in ledger.sheets if sheet.marks],
        }
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "CodeMaster/0.2"
    protocol_version = "HTTP/1.0"

    def log_message(self, _format: str, *args: Any) -> None:
        return

    # ------------------------------------------------------------ helpers

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            decoded = self.rfile.read(length).decode("utf-8")
            payload: Any = json.loads(decoded)
            return payload if isinstance(payload, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    # ---------------------------------------------------------------- GET

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/" or route == "/index.html":
            self._serve_index()
            return
        if route == "/api/scan":
            self._scan(query)
            return
        if route == "/api/report":
            self._report(query)
            return
        if route == "/api/history":
            self._send_json({"entries": history.load()})
            return
        if route == "/api/config":
            self._send_json(vars(load_config()))
            return
        if route == "/api/list":
            self._list_dir(query)
            return
        self._send_json({"error": "not found"}, 404)

    def _serve_index(self) -> None:
        try:
            body = _HTML.read_bytes()
        except OSError:
            body = b"<html><body><h1>CodeMaster</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _list_dir(self, query: dict[str, list[str]]) -> None:
        raw = query.get("path", [""])[0]
        start = Path(raw) if raw else Path.home()
        if not start.is_dir():
            start = start.parent if start.exists() else Path.home()
        try:
            dirs = sorted(
                (
                    Path(p)
                    for p in start.iterdir()
                    if p.is_dir() and not p.name.startswith(".") and not p.is_symlink()
                ),
                key=lambda p: p.name.lower(),
            )
        except OSError:
            dirs = []
        self._send_json(
            {
                "path": str(start),
                "parent": str(start.parent) if start.parent != start else None,
                "dirs": [{"name": d.name, "path": str(d)} for d in dirs[:500]],
            }
        )

    def _scan(self, query: dict[str, list[str]]) -> None:
        raw = query.get("path", [""])[0]
        if not raw:
            self._send_json({"error": "path requerido"}, 400)
            return
        root = Path(raw)
        if not root.exists():
            self._send_json({"error": "ruta invalida"}, 400)
            return
        scope = _scope_from(query)
        config = load_config()
        stream = query.get("stream", ["1"])[0] != "0"
        if not stream:
            self._scan_sync(root, scope, config)
            return
        self._scan_stream(root, scope, config)

    def _scan_sync(self, root: Path, scope: Scope, config: Config) -> None:
        events: list[dict[str, Any]] = []

        def emit(payload: dict[str, Any]) -> None:
            events.append(payload)

        _run_scan([root], scope, config, emit)
        final = next(e for e in events if e["type"] == "done")
        self._send_json(final)

    def _scan_stream(self, root: Path, scope: Scope, config: Config) -> None:
        events: queue.Queue[dict[str, Any]] = queue.Queue()

        def emit(payload: dict[str, Any]) -> None:
            events.put(payload)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 500\n\n")
            self.wfile.flush()
        except OSError:
            return

        def worker() -> None:
            try:
                _run_scan([root], scope, config, emit)
            except Exception as exc:  # pragma: no cover - defensive
                emit({"type": "error", "error": str(exc)})
                emit({"type": "done", "totals": {}, "worst": "hush", "files": []})

        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                try:
                    event = events.get(timeout=1.0)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                if event.get("type") == "done":
                    break
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _report(self, query: dict[str, list[str]]) -> None:
        raw = query.get("path", [""])[0]
        fmt = query.get("format", ["human"])[0]
        scope = _scope_from(query)
        roots = [Path(raw)] if raw else [Path(".")]
        ledger = portal.tour(roots, scope)
        if fmt == "json":
            body = render_json(ledger)
            ctype = "application/json"
        elif fmt == "md":
            body = render_markdown(ledger)
            ctype = "text/markdown"
        elif fmt == "html":
            body = render_html(ledger)
            ctype = "text/html"
        else:
            body = render_json(ledger)
            ctype = "application/json"
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # --------------------------------------------------------------- POST

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/api/clean":
            self._clean()
            return
        if route == "/api/config":
            self._save_config()
            return
        self._send_json({"error": "not found"}, 404)

    def _clean(self) -> None:
        payload = self._read_json()
        paths = payload.get("paths", [])
        if not paths:
            self._send_json({"error": "paths requerido"}, 400)
            return
        scope = _scope_from({})
        config = load_config()
        edits = Edits(
            comments=payload.get("comments", config.comments),
            docstrings=payload.get("docstrings", config.docstrings),
            glyphs=payload.get("glyphs", config.glyphs),
            meta=payload.get("meta", config.meta),
        )
        backup = bool(payload.get("backup", config.backup))
        results = [
            portal.wash_path(Path(p), edits, scope, backup=backup, apply_write=True)
            for p in paths
        ]
        history.record(results, source="web", backup=backup)
        self._send_json(
            {
                "washed": sum(1 for r in results if r.written),
                "results": [
                    {
                        "path": str(r.path),
                        "written": r.written,
                        "labels": r.labels,
                        "backup": str(r.backup) if r.backup is not None else None,
                    }
                    for r in results
                ],
            }
        )

    def _save_config(self) -> None:
        payload = self._read_json()
        config = load_config()
        for key in ("workers", "backup", "comments", "docstrings", "meta", "glyphs"):
            if key in payload:
                value = payload[key]
                if isinstance(value, (int, float, str, bool)):
                    setattr(config, key, value)
        save_config(config)
        self._send_json({"saved": True, "config": vars(config)})


class _Server(ThreadingHTTPServer):
    daemon_threads = True


def serve(host: str = "127.0.0.1", port: int = 8765) -> _Server:
    return _Server((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="codemaster-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    ns = parser.parse_args(argv)
    server = serve(ns.host, ns.port)
    print(f"CodeMaster web en http://{ns.host}:{ns.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
