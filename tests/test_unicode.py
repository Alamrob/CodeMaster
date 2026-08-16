from __future__ import annotations

from codemaster.report import Grade
from codemaster.unicode import flush, probe, stealth_ranges


def test_stealth_detected() -> None:
    text = "a" + "\u200b" + "b"
    slips = probe(text)
    assert len(slips) == 1
    assert slips[0].kind == "stealth"
    assert slips[0].rank is Grade.DANGER
    assert slips[0].col == 2


def test_foreign_cf_flagged_as_signal() -> None:
    text = "x\U000e0001y"
    slips = probe(text)
    assert any(slip.kind == "foreign" and slip.rank is Grade.SIGNAL for slip in slips)


def test_plain_text_silent() -> None:
    assert probe("alpha beta gamma") == []


def test_accented_letters_not_flagged() -> None:
    assert probe("década café") == []


def test_flush_removes_stealth_only() -> None:
    text = "a\u200bb\u202ec"
    assert flush(text) == "abc"


def test_stealth_ranges_cover_whole_run() -> None:
    text = "a" + "\u200b\u200b" + "b"
    assert stealth_ranges(text) == [(1, 3)]
