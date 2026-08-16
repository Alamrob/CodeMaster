from __future__ import annotations

from pathlib import Path

import pytest

from codemaster.handlers import _deps, visible

BANANA = (
    Path(__file__).resolve().parent.parent
    / "remove-ai-watermarks-main"
    / "demo_banana_before.png"
)


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_detects_synthetic_sparkle() -> None:
    np = _deps.load("numpy")
    image = np.full((2048, 2048, 3), 60, np.uint8)
    alpha = visible.load_alpha("gemini_bg_96.png")
    x, y = 2048 - 64 - 96, 2048 - 64 - 96
    region = image[y : y + 96, x : x + 96].astype(np.float32)
    image[y : y + 96, x : x + 96] = (
        255.0 * alpha[:, :, None] + region * (1.0 - alpha[:, :, None])
    ).astype(np.uint8)
    det = visible.detect_gemini(image)
    assert det is not None, "sparkle should be detected"
    assert det.key == "gemini"
    assert det.confidence >= 0.5


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_absent_on_clean_image() -> None:
    np = _deps.load("numpy")
    image = np.full((2048, 2048, 3), 120, np.uint8)
    assert visible.detect_gemini(image) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_on_real_reference_image() -> None:
    if not BANANA.exists():
        pytest.skip("reference demo image missing")
    cv2 = _deps.load("cv2")
    image = cv2.imread(str(BANANA), cv2.IMREAD_COLOR)
    assert image is not None
    found = [d for d in visible.detect_all(image) if d.key == "gemini"]
    assert found, "real Gemini sparkle must be detected on the reference image"
    cleaned, labels = visible.remove_marks(image)
    assert any("sparkle" in label for label in labels)
    residual = visible.detect_gemini(cleaned)
    if residual is not None:
        assert residual.confidence < found[0].confidence


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_doubao_text_mark_detected_and_removed() -> None:
    np = _deps.load("numpy")
    image = np.full((2048, 2048, 3), 60, np.uint8)
    alpha = visible.load_alpha("doubao_alpha.png")
    gw, gh = int(0.1636 * 2048), int(0.0405 * 2048)
    resized = _resize(alpha, gw, gh)
    x, y = 2048 - 8 - gw, 2048 - 8 - gh
    region = image[y : y + gh, x : x + gw].astype(np.float32)
    image[y : y + gh, x : x + gw] = (
        255.0 * resized[:, :, None] + region * (1.0 - resized[:, :, None])
    ).astype(np.uint8)
    found = [d for d in visible.detect_all(image) if d.key == "doubao"]
    assert found, "synthetic Doubao strip must be detected"
    cleaned, labels = visible.remove_marks(image)
    assert any("Doubao" in label for label in labels)
    residual = [d for d in visible.detect_all(cleaned) if d.key == "doubao"]
    assert not residual


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_clean_image_has_no_marks() -> None:
    np = _deps.load("numpy")
    image = np.full((1200, 1600, 3), 90, np.uint8)
    assert visible.detect_all(image) == []


def _resize(alpha, gw: int, gh: int):
    cv2 = _deps.load("cv2")
    return cv2.resize(alpha, (gw, gh), interpolation=cv2.INTER_AREA)
