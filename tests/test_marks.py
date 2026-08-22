from __future__ import annotations

from codemaster import marks
from codemaster.handlers import visible


def test_marks_catalog_loaded() -> None:
    assert len(marks.REGISTRY) >= 8
    keys = {m.key for m in marks.REGISTRY}
    assert {
        "doubao",
        "jimeng",
        "qwen",
        "kling",
        "yuanbao",
        "samsung",
        "runninghub",
        "baidu",
        "liblib",
    } <= keys


def test_visible_uses_catalog() -> None:
    assert visible._MARKS == marks.REGISTRY
    assert [m.key for m in visible._MARKS] == [m.key for m in marks.REGISTRY]


def test_marks_required_fields() -> None:
    for mark in marks.REGISTRY:
        assert mark.key
        assert mark.asset_name
        assert mark.corner in ("br", "bl", "tl", "bc")
        assert mark.width_frac > 0
        assert mark.detect_frontend in ("tophat", "binary", "contrast", "gray")
        assert mark.ladder


def test_mark_config_defaults(tmp_path) -> None:

    cfg = tmp_path / "extra.toml"
    cfg.write_text(
        '[[marks]]\nkey = "mybrand"\nasset = "mybrand_alpha.png"\n',
        encoding="utf-8",
    )
    loaded = marks.load(cfg)
    assert len(loaded) == 1
    mark = loaded[0]
    assert mark.key == "mybrand"
    assert mark.corner == "br"
    assert mark.detect_frontend == "tophat"
    assert mark.min_short_side == 200
