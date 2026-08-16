from __future__ import annotations

from codemaster.report import Grade
from codemaster.tokens import collect


def test_comment_location_flagged(tainted_py) -> None:
    slips = collect(tainted_py.read_text(encoding="utf-8"))
    kinds = {slip.kind for slip in slips}
    assert "comment" in kinds
    assert "docstring" in kinds
    comment = next(slip for slip in slips if slip.kind == "comment")
    assert comment.line == 2
    assert comment.rank is Grade.DANGER


def test_docstring_detected(tainted_py) -> None:
    slips = collect(tainted_py.read_text(encoding="utf-8"))
    docstring = next(slip for slip in slips if slip.kind == "docstring")
    assert docstring.line == 3
    assert "merge two arrays" in docstring.note


def test_clean_module_silent(clean_mod) -> None:
    assert collect(clean_mod.read_text(encoding="utf-8")) == []


def test_string_assignment_is_not_docstring() -> None:
    source = 'label = "a value"\ndef work():\n    return 1\n'
    assert all(slip.kind != "docstring" for slip in collect(source))


def test_malformed_source_still_reports_comments() -> None:
    source = "def broken(:\n    # inline note\n    pass\n"
    slips = collect(source)
    assert any(slip.kind == "comment" for slip in slips)
    assert any(slip.kind == "malformed" for slip in slips)
