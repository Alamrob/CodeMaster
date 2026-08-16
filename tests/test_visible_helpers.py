from __future__ import annotations

import pytest

from codemaster.handlers import _deps, visible


@pytest.fixture()
def np():
    return _deps.load("numpy")


@pytest.fixture()
def cv2():
    return _deps.load("cv2")


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_to_bgr_variants(np) -> None:
    gray = np.zeros((8, 8), np.uint8)
    rgb = np.zeros((8, 8, 3), np.uint8)
    rgba = np.zeros((8, 8, 4), np.uint8)
    assert visible._to_bgr(gray).shape == (8, 8, 3)
    assert visible._to_bgr(rgb).shape == (8, 8, 3)
    assert visible._to_bgr(rgba).shape == (8, 8, 3)


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_scale_base_semantics(np) -> None:
    image = np.zeros((60, 120, 3), np.uint8)
    short = next(c for c in visible._MARKS if c.scale_basis == "short")
    width = next(c for c in visible._MARKS if c.scale_basis == "width")
    assert visible._scale_base(short, image) == 60
    assert visible._scale_base(width, image) == 120


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_locate_all_corners_in_bounds(np) -> None:
    image = np.zeros((300, 500, 3), np.uint8)
    for cfg in visible._MARKS:
        x, y, bw, bh = visible._locate(cfg, image)
        assert x >= 0 and x + bw <= 500
        assert y >= 0 and y + bh <= 300
        assert bw > 0 and bh > 0


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_mask_for_invalid_fill_box_returns_none(np) -> None:
    from codemaster.handlers.visible import Detection

    image = np.zeros((100, 100, 3), np.uint8)
    det = Detection("gemini", "sparkle", 0.9, (50, 50, 20, 20), (0, 0, 0, 0))
    assert visible.mask_for(det, image) is None


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_mask_for_fill_box_dilates(np) -> None:
    from codemaster.handlers.visible import Detection

    image = np.zeros((100, 100, 3), np.uint8)
    det = Detection("gemini", "sparkle", 0.9, (50, 50, 20, 20), (60, 60, 70, 70))
    mask = visible.mask_for(det, image)
    assert mask is not None
    assert mask.shape == (100, 100)
    assert int(mask.sum()) > 0


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_footprint_indices_clipped(np) -> None:
    alpha = np.ones((10, 10), np.float32)
    out_of_frame = visible._footprint_indices(alpha, (60, 60), (50, 50))
    assert out_of_frame is None
    partial = visible._footprint_indices(alpha, (45, 45), (50, 50))
    assert partial is not None
    clipped, (y1, y2, x1, x2) = partial
    assert (y2 - y1) == 5
    assert (x2 - x1) == 5
    assert clipped.shape == (5, 5)


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_overlaps_semantics() -> None:
    assert visible._overlaps((10, 5, 5, 1.0), (10, 6, 6, 1.0))
    assert not visible._overlaps((10, 5, 5, 1.0), (10, 200, 200, 1.0))


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_gemini_interpolated_alpha_same_size_fast_path(np, cv2) -> None:
    large = visible.load_alpha("gemini_bg_96.png")
    if large is None:
        pytest.skip("gemini alpha asset missing")
    same = visible._gemini_interpolated_alpha(large.shape[1])
    assert same.shape == large.shape
    up = visible._gemini_interpolated_alpha(large.shape[1] + 20)
    assert up.shape == (large.shape[1] + 20,) * 2
    down = visible._gemini_interpolated_alpha(large.shape[1] - 20)
    assert down.shape == (large.shape[1] - 20,) * 2


@pytest.mark.skipif(not visible.available(), reason="pixels extra absent")
def test_remove_marks_clean_image_unchanged(np) -> None:
    image = np.full((1200, 1600, 3), 90, np.uint8)
    cleaned, labels = visible.remove_marks(image)
    assert labels == []
    assert (cleaned == image).all()


def test_available_reports_false_when_deps_missing(monkeypatch) -> None:
    def fake_load(name):
        return None

    monkeypatch.setattr(_deps, "load", fake_load)
    assert not visible.available()


def test_load_alpha_missing_file(np, monkeypatch) -> None:
    monkeypatch.setattr(visible, "_ASSET_DIR", _asset_dir_missing())
    assert visible.load_alpha("nope.png") is None
    assert visible.glyph_silhouette("nope.png") is None


def _asset_dir_missing():
    from pathlib import Path

    return Path(__file__).resolve().parent / "no-such-assets"
