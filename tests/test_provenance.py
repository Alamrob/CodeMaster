from __future__ import annotations

from pathlib import Path

import pytest

from codemaster._internal import rich
from codemaster.handlers import _deps
from codemaster.handlers import image_meta as im

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA = _REPO_ROOT / "remove-ai-watermarks-main" / "data"

_CHATGPT = (
    _DATA / "synthid" / "originals" / "ChatGPT Image May 30, 2026, 10_31_08 AM.png"
)
_GEMINI = (
    _DATA / "synthid" / "originals" / "Gemini_Generated_Image_3mc4t93mc4t93mc4.png"
)
_FIREFLY = _DATA / "fixtures" / "provenance" / "firefly-1.png"
_FLUX = _DATA / "fixtures" / "provenance" / "flux-1.jpg"


def _info(path: Path) -> dict:
    return rich.c2pa_info(path.read_bytes())


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _CHATGPT.exists(), reason="OpenAI C2PA fixture absent")
def test_openai_fixture_verdict() -> None:
    info = _info(_CHATGPT)
    assert info is not None
    assert info.get("vendor") == "OpenAI"
    assert info.get("ai") is True
    assert info.get("watermarked") is True


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _GEMINI.exists(), reason="Google C2PA fixture absent")
def test_gemini_fixture_detects_synthid() -> None:
    info = _info(_GEMINI)
    assert info is not None
    assert info.get("vendor") == "Google"
    assert info.get("synthid") == "Google"
    assert info.get("ai") is True


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _GEMINI.exists(), reason="Google C2PA fixture absent")
def test_gemini_audit_reports_synthid_slip() -> None:
    slips = im._png_audit(_GEMINI.read_bytes())
    notes = [s.note for s in slips if s.kind == "c2pa"]
    assert any("synthid watermark present" in note for note in notes)
    assert any("vendor: Google" in note for note in notes)


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _FIREFLY.exists(), reason="Adobe C2PA fixture absent")
def test_firefly_fixture_no_synthid() -> None:
    info = _info(_FIREFLY)
    assert info is not None
    assert info.get("vendor") == "Adobe"
    assert "synthid" not in info


@pytest.mark.skipif(not _deps.c2pa_ok(), reason="c2pa extra absent")
@pytest.mark.skipif(not _FLUX.exists(), reason="FLUX C2PA fixture absent")
def test_flux_fixture_vendor() -> None:
    info = _info(_FLUX)
    assert info is not None
    assert info.get("vendor") == "Black Forest Labs"
    assert info.get("ai") is True
