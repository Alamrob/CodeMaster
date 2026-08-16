from __future__ import annotations

from dataclasses import replace

import pytest

from codemaster.handlers import _deps, visible
from codemaster.handlers.visible import Detection


@pytest.fixture()
def np():
    return _deps.load("numpy")


def _image(np, h=100, w=100):
    return np.zeros((h, w, 3), np.uint8)


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_load_alpha_none_when_cv2_missing(np, monkeypatch) -> None:
    monkeypatch.setattr(visible, "_cv2", lambda: None)
    assert visible.load_alpha("nosuch_asset.png") is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_load_alpha_none_when_imread_fails(np, monkeypatch) -> None:
    monkeypatch.setattr(visible, "_alpha_cache", {})
    monkeypatch.setattr(visible, "_sil_cache", {})

    class FakeCv:
        IMREAD_GRAYSCALE = 0

        def imread(self, path, flag):
            return None

    monkeypatch.setattr(visible, "_cv2", lambda: FakeCv())
    assert visible.load_alpha("doubao_alpha.png") is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_detect_all_when_unavailable(np, monkeypatch) -> None:
    monkeypatch.setattr(visible, "available", lambda: False)
    assert visible.detect_all(_image(np)) == []


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_remove_marks_skips_empty_mask(np, monkeypatch) -> None:
    image = _image(np)
    det = Detection("gemini", "sparkle", 0.9, (50, 50, 20, 20), (0, 0, 0, 0))
    monkeypatch.setattr(visible, "detect_all", lambda img: [det])
    result, labels = visible.remove_marks(image)
    assert labels == []
    assert (result == image).all()


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_extract_mask_small_region_zeros(np) -> None:
    cfg = visible._MARKS[0]
    out = visible._extract_mask(cfg, _image(np), (0, 0, 8, 8))
    assert out.shape == (8, 8)
    assert not out.any()


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_template_match_score_sil_none(np, monkeypatch) -> None:
    cfg = visible._MARKS[0]
    monkeypatch.setattr(visible, "glyph_silhouette", lambda name: None)
    assert visible._template_match_score(cfg, np.ones((20, 20), np.uint8), 100) == 0.0


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_template_match_score_too_small(np) -> None:
    cfg = visible._MARKS[0]
    box = np.ones((3, 3), np.uint8)
    assert visible._template_match_score(cfg, box, 100) == 0.0


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_residual_response_small_region_none(np) -> None:
    cfg = visible._MARKS[0]
    assert visible._residual_response(cfg, _image(np), (0, 0, 8, 8), False) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_detect_response_gray_small_none(np) -> None:
    cfg = next(c for c in visible._MARKS if c.detect_frontend == "gray")
    assert visible._detect_response(cfg, _image(np), (0, 0, 8, 8)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_detect_response_unknown_frontend_none(np) -> None:
    cfg = replace(visible._MARKS[0], detect_frontend="other")
    assert visible._detect_response(cfg, _image(np), (0, 0, 20, 20)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_ladder_best_skips_large_scale(np, monkeypatch) -> None:
    cfg = visible._MARKS[0]
    monkeypatch.setattr(
        visible, "_detect_response", lambda cfg_, img, loc: np.zeros((10, 10), np.uint8)
    )
    score, box = visible._ladder_best(cfg, _image(np, 100, 100), (0, 0, 20, 20))
    assert score == 0.0
    assert box is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_footprint_rect_match_box_path(np) -> None:
    cfg = next(c for c in visible._MARKS if c.detect_frontend == "tophat")
    image = _image(np, 300, 500)
    loc = visible._locate(cfg, image)
    box = np.zeros((loc[3], loc[2]), np.uint8)
    rect = visible._footprint_rect(cfg, image, loc, box, (0, 0, 20, 20))
    assert rect is not None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_footprint_rect_blob_too_small_none(np) -> None:
    cfg = next(c for c in visible._MARKS if c.detect_frontend == "binary")
    image = _image(np, 300, 500)
    loc = visible._locate(cfg, image)
    box = np.zeros((loc[3], loc[2]), np.uint8)
    rect = visible._footprint_rect(cfg, image, loc, box, None)
    assert rect is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_footprint_rect_blob_large_binary(np) -> None:
    cfg = next(c for c in visible._MARKS if c.detect_frontend == "binary")
    image = _image(np, 300, 500)
    loc = visible._locate(cfg, image)
    box = np.zeros((loc[3], loc[2]), np.uint8)
    box[4:8, 4:60] = 255
    rect = visible._footprint_rect(cfg, image, loc, box, None)
    assert rect is not None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_footprint_rect_baidu_padding(np) -> None:
    cfg = next(c for c in visible._MARKS if c.key == "baidu")
    image = _image(np, 300, 500)
    loc = visible._locate(cfg, image)
    box = np.zeros((loc[3], loc[2]), np.uint8)
    rect = visible._footprint_rect(cfg, image, loc, box, (0, 0, 20, 20))
    assert rect is not None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_footprint_rect_liblib_padding(np) -> None:
    cfg = next(c for c in visible._MARKS if c.key == "liblib")
    image = _image(np, 600, 800)
    loc = visible._locate(cfg, image)
    box = np.zeros((loc[3], loc[2]), np.uint8)
    rect = visible._footprint_rect(cfg, image, loc, box, (0, 0, 20, 20))
    assert rect is not None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_mask_for_gemini_out_of_frame_none(np, monkeypatch) -> None:
    image = _image(np)
    det = Detection("gemini", "sparkle", 0.9, (150, 150, 20, 20))
    monkeypatch.setattr(
        visible,
        "_gemini_interpolated_alpha",
        lambda size: np.full((size, size), 0.5, np.float32),
    )
    assert visible.mask_for(det, image) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_mask_for_gemini_empty_silhouette_none(np, monkeypatch) -> None:
    image = _image(np)
    det = Detection("gemini", "sparkle", 0.9, (0, 0, 20, 20))
    monkeypatch.setattr(
        visible,
        "_gemini_interpolated_alpha",
        lambda size: np.zeros((size, size), np.float32),
    )
    assert visible.mask_for(det, image) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_inpaint_rgba_keeps_alpha(np) -> None:
    rgba = np.zeros((50, 50, 4), np.uint8)
    mask = np.zeros((50, 50), np.uint8)
    out = visible._inpaint(rgba, mask)
    assert out.shape == (50, 50, 4)
    assert (out[:, :, 3] == 0).all()


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_interpolated_alpha_missing_large(np, monkeypatch) -> None:
    monkeypatch.setattr(visible, "load_alpha", lambda name: None)
    assert visible._gemini_interpolated_alpha(48) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_and_bg_out_of_frame_none(np, monkeypatch) -> None:
    image = _image(np)
    alpha = np.full((20, 20), 0.5, np.float32)
    assert visible._gemini_core_and_bg(image, alpha, (150, 150)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_and_bg_low_peak_none(np) -> None:
    image = _image(np)
    alpha = np.zeros((20, 20), np.float32)
    assert visible._gemini_core_and_bg(image, alpha, (0, 0)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_and_bg_nan_core_none(np) -> None:
    image = _image(np)
    alpha = np.full((20, 20), np.nan, np.float32)
    assert visible._gemini_core_and_bg(image, alpha, (0, 0)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_and_bg_tiny_background_none(np) -> None:
    image = _image(np, 30, 30)
    alpha = np.full((30, 30), 0.5, np.float32)
    assert visible._gemini_core_and_bg(image, alpha, (0, 0)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_saturation_out_of_frame_none(np) -> None:
    image = _image(np)
    alpha = np.full((20, 20), 0.5, np.float32)
    assert visible._gemini_core_saturation(image, alpha, (150, 150)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_saturation_low_peak_none(np) -> None:
    image = _image(np)
    alpha = np.zeros((20, 20), np.float32)
    assert visible._gemini_core_saturation(image, alpha, (0, 0)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_core_saturation_nan_core_none(np) -> None:
    image = _image(np)
    alpha = np.full((20, 20), np.nan, np.float32)
    assert visible._gemini_core_saturation(image, alpha, (0, 0)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_detect_gemini_when_unavailable(np, monkeypatch) -> None:
    monkeypatch.setattr(visible, "available", lambda: False)
    assert visible.detect_gemini(_image(np)) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_fp_gate_returns_fused(np, monkeypatch) -> None:
    image = _image(np, 300, 300)
    cand = (24, 250, 250, 0.60)
    monkeypatch.setattr(visible, "_gemini_core_and_bg", lambda *a: (200.0, 120.0, 0.9))
    monkeypatch.setattr(visible, "_gemini_grad_var", lambda *a: (0.9, 0.2))
    monkeypatch.setattr(visible, "_gemini_core_saturation", lambda *a: 0.10)
    monkeypatch.setattr(visible, "_gemini_fused", lambda img, c: 0.7)
    assert visible._gemini_fp_gate(image, cand) == 0.7


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_fp_gate_caps_at_keep(np, monkeypatch) -> None:
    image = _image(np, 300, 300)
    cand = (24, 250, 250, 0.60)
    monkeypatch.setattr(visible, "_gemini_core_and_bg", lambda *a: (120.0, 200.0, 0.9))
    monkeypatch.setattr(visible, "_gemini_grad_var", lambda *a: (0.2, 0.9))
    monkeypatch.setattr(visible, "_gemini_core_saturation", lambda *a: 0.9)
    monkeypatch.setattr(visible, "_gemini_fused", lambda img, c: 0.7)
    assert visible._gemini_fp_gate(image, cand) == 0.30


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_fp_gate_neutral_core_keeps(np, monkeypatch) -> None:
    image = _image(np, 300, 300)
    cand = (24, 250, 250, 0.60)
    monkeypatch.setattr(visible, "_gemini_core_and_bg", lambda *a: (200.0, 120.0, 0.9))
    monkeypatch.setattr(visible, "_gemini_grad_var", lambda *a: (0.2, 0.9))
    monkeypatch.setattr(visible, "_gemini_core_saturation", lambda *a: 0.10)
    monkeypatch.setattr(visible, "_gemini_fused", lambda img, c: 0.7)
    assert visible._gemini_fp_gate(image, cand) == 0.7
