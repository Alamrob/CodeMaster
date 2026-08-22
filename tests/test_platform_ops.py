from __future__ import annotations

from pathlib import Path

from codemaster import config
from codemaster.history import load, record
from codemaster.scrubber import WashResult


def test_config_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "cfg.json"
    cfg = config.Config(workers=7, backup=False, glyphs=True, strong_only=True)
    config.save(cfg, target)
    loaded = config.load(target)
    assert loaded.workers == 7
    assert loaded.backup is False
    assert loaded.glyphs is True
    assert loaded.strong_only is True
    assert loaded.edits().glyphs is True


def test_config_missing_returns_defaults(tmp_path: Path) -> None:
    loaded = config.load(tmp_path / "nope.json")
    assert loaded.workers == 0
    assert loaded.backup is True


def test_config_ignores_unknown_keys(tmp_path: Path) -> None:
    target = tmp_path / "cfg.json"
    target.write_text('{"workers": 3, "hack": "x", "comments": "no"}', encoding="utf-8")
    loaded = config.load(target)
    assert loaded.workers == 3
    assert loaded.comments is True


def test_history_records_only_written(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "codemaster.history.history_dir", lambda: tmp_path / ".codemaster"
    )
    results = [
        WashResult(Path("a.py"), True, ["comments"], Path("a.py.bak"), True),
        WashResult(Path("b.py"), True, ["glyphs"], None, False),
        WashResult(Path("c.py"), False, [], None, False),
    ]
    record(results, source="test", backup=True)
    entries = load()
    assert len(entries) == 1
    assert entries[0]["path"].endswith("a.py")
    assert entries[0]["labels"] == ["comments"]
    assert entries[0]["backup_path"].endswith("a.py.bak")
    assert (tmp_path / ".codemaster" / "history.jsonl").exists()


def test_history_load_missing_is_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "codemaster.history.history_dir", lambda: tmp_path / ".codemaster"
    )
    assert load() == []
