from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codemaster.handlers import _deps

_ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"

_alpha_cache: dict[str, Any] = {}
_sil_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class MarkConfig:
    key: str
    label: str
    asset_name: str
    corner: str
    margin_floor: int
    width_frac: float
    height_frac: float
    margin_x_frac: float
    margin_bottom_frac: float
    max_saturation: int
    logo_min_luma: int
    tophat_delta: int
    morph_open_size: int
    detect_ncc_threshold: float
    detect_frontend: str
    scale_basis: str
    ladder: tuple[float, ...]
    alpha_width_frac: float
    alpha_height_frac: float
    min_gw: int
    min_short_side: int = 200


@dataclass
class Detection:
    key: str
    label: str
    confidence: float
    region: tuple[int, int, int, int]
    fill_box: tuple[int, int, int, int] | None = None


_MARKS: tuple[MarkConfig, ...] = (
    MarkConfig(
        "doubao",
        "Doubao 豆包AI生成 text",
        "doubao_alpha.png",
        "br",
        4,
        0.22,
        0.075,
        0.004,
        0.004,
        55,
        150,
        12,
        5,
        0.50,
        "tophat",
        "short",
        (0.8, 1.0, 1.25),
        0.1636,
        0.0405,
        8,
    ),
    MarkConfig(
        "jimeng",
        "Jimeng 即梦AI wordmark",
        "jimeng_alpha.png",
        "br",
        4,
        0.27,
        0.092,
        0.008,
        0.010,
        55,
        150,
        12,
        5,
        0.45,
        "binary",
        "width",
        (0.8, 1.0, 1.25),
        0.2021,
        0.0576,
        8,
    ),
    MarkConfig(
        "qwen",
        "Qwen 千问AI生成 text",
        "qwen_alpha.png",
        "br",
        4,
        0.231,
        0.074,
        0.0203,
        0.0218,
        55,
        150,
        12,
        5,
        0.45,
        "tophat",
        "short",
        (0.78, 1.27),
        0.160,
        0.0416,
        8,
    ),
    MarkConfig(
        "kling",
        "Kling 可灵AI 3.0 text",
        "kling_alpha.png",
        "br",
        4,
        0.19,
        0.05,
        0.03,
        0.023,
        55,
        150,
        12,
        5,
        0.35,
        "tophat",
        "short",
        (0.8, 1.0, 1.25),
        0.12,
        0.0287,
        8,
    ),
    MarkConfig(
        "yuanbao",
        "Tencent Yuanbao 元宝 / AI生成 mark",
        "yuanbao_alpha.png",
        "br",
        4,
        0.20,
        0.15,
        0.002,
        0.002,
        55,
        150,
        12,
        5,
        0.38,
        "contrast",
        "short",
        (0.95, 1.0, 1.05),
        0.08,
        0.0446,
        32,
    ),
    MarkConfig(
        "samsung",
        "Samsung Galaxy AI text",
        "samsung_alpha.png",
        "bl",
        2,
        0.40,
        0.060,
        0.004,
        0.002,
        55,
        110,
        8,
        3,
        0.40,
        "binary",
        "width",
        (0.8, 1.0, 1.25),
        0.3195,
        0.0378,
        16,
    ),
    MarkConfig(
        "runninghub",
        "RunningHub AI生成 text",
        "runninghub_alpha.png",
        "tl",
        4,
        0.45,
        0.10,
        0.002,
        0.002,
        55,
        150,
        12,
        5,
        0.34,
        "gray",
        "width",
        (0.95, 1.0, 1.05),
        0.32,
        0.04,
        8,
    ),
    MarkConfig(
        "baidu",
        "Baidu 百度 AI生成 text",
        "baidu_alpha.png",
        "br",
        4,
        0.25,
        0.07,
        0.002,
        0.002,
        55,
        150,
        12,
        5,
        0.48,
        "tophat",
        "short",
        (0.95, 1.0, 1.05),
        0.090,
        0.046,
        8,
    ),
    MarkConfig(
        "liblib",
        "LibLibAI wordmark",
        "liblib_alpha.png",
        "bc",
        4,
        0.20,
        0.09,
        0.0,
        0.02,
        55,
        150,
        12,
        5,
        0.42,
        "tophat",
        "width",
        (0.9, 1.0, 1.1),
        0.10,
        0.026,
        8,
        min_short_side=480,
    ),
)

_GEMINI_SMALL = "gemini_bg_48.png"
_GEMINI_LARGE = "gemini_bg_96.png"
_TEMPLATE_SCALES = tuple(range(16, 120, 2))
_FP_CONF = 0.65
_FP_MARGIN = 5.0
_FP_GRAD = 0.55
_KEEP_CONF = 0.52
_WHITE_SAT = 0.20
_CORNER_PROMOTE_NCC = 0.85
_CORNER_PROMOTE_FRAC = 0.20
_CORNER_PROMOTE_MIN = 96
_CORNER_PROMOTE_MAX = 384
_SELECT_TOPK = 3
_MASK_ALPHA = 0.04
_MASK_DILATE_FRAC = 0.18
_CORE_ALPHA_FRAC = 0.8
_GEMINI_TRUST_CONF = 0.5


def available() -> bool:
    return bool(_deps.load("numpy") and _deps.load("cv2"))


def _cv2() -> Any:
    return _deps.load("cv2")


def _np() -> Any:
    return _deps.load("numpy")


def load_alpha(asset_name: str) -> Any:
    cached = _alpha_cache.get(asset_name)
    if cached is not None:
        return cached
    cv2, np = _cv2(), _np()
    if not cv2 or not np:
        return None
    path = _ASSET_DIR / asset_name
    if not path.exists():
        return None
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    _alpha_cache[asset_name] = img.astype(np.float32) / 255.0
    return _alpha_cache[asset_name]


def glyph_silhouette(asset_name: str) -> Any:
    cached = _sil_cache.get(asset_name)
    if cached is not None:
        return cached
    at = load_alpha(asset_name)
    if at is None:
        return None
    np = _np()
    _sil_cache[asset_name] = ((at > 0.15) * 255).astype(np.uint8)
    return _sil_cache[asset_name]


def detect_all(image: Any) -> list[Detection]:
    if not available():
        return []
    source = _to_bgr(image)
    out: list[Detection] = []
    gemini = detect_gemini(source)
    if gemini is not None:
        out.append(gemini)
    for cfg in _MARKS:
        det = _detect_text(cfg, source)
        if det is not None:
            out.append(det)
    return out


def remove_marks(image: Any) -> tuple[Any, list[str]]:
    source = _to_bgr(image)
    result = source
    labels: list[str] = []
    for det in detect_all(source):
        mask = mask_for(det, source)
        if mask is None or not mask.any():
            continue
        result = _inpaint(result, mask)
        labels.append(det.label)
    return result, labels


# helpers


def _to_bgr(image: Any) -> Any:
    cv2 = _cv2()
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        return image[:, :, :3]
    return image


def _gray_float(image: Any) -> Any:
    cv2 = _cv2()
    gray = (
        cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if image.ndim == 3 and image.shape[2] >= 3
        else image
    )
    return gray.astype(_np().float32) / 255.0


def _scale_base(cfg: MarkConfig, image: Any) -> int:
    return (
        int(min(image.shape[:2])) if cfg.scale_basis == "short" else int(image.shape[1])
    )


def _locate(cfg: MarkConfig, image: Any) -> tuple[int, int, int, int]:
    h, w = image.shape[:2]
    base = _scale_base(cfg, image)
    wm_w = max(40, int(base * cfg.width_frac))
    wm_h = max(16, int(base * cfg.height_frac))
    margin_x = max(cfg.margin_floor, int(base * cfg.margin_x_frac))
    margin_b = max(cfg.margin_floor, int(base * cfg.margin_bottom_frac))
    if cfg.corner == "br":
        x = max(0, w - margin_x - wm_w)
    elif cfg.corner == "bc":
        x = max(0, (w - wm_w) // 2)
    else:
        x = min(margin_x, max(0, w - wm_w))
    y = (
        min(margin_b, max(0, h - wm_h))
        if cfg.corner == "tl"
        else max(0, h - margin_b - wm_h)
    )
    wm_w = min(wm_w, w - x)
    wm_h = min(wm_h, h - y)
    return x, y, wm_w, wm_h


def _extract_mask(cfg: MarkConfig, image: Any, loc: tuple[int, int, int, int]) -> Any:
    cv2, np = _cv2(), _np()
    x, y, bw, bh = loc
    if bh < 16 or bw < 16:
        return np.zeros((bh, bw), np.uint8)
    roi = _to_bgr(image[y : y + bh, x : x + bw]).astype(np.float32)
    luma = roi.mean(axis=2)
    sat = roi.max(axis=2) - roi.min(axis=2)
    grayish = sat < cfg.max_saturation
    sigma = max(4.0, bh * 0.4)
    local_bg = cv2.GaussianBlur(luma, (0, 0), sigmaX=sigma, sigmaY=sigma)
    tophat = luma - local_bg
    cand = grayish & (tophat > cfg.tophat_delta) & (luma > cfg.logo_min_luma)
    glyph = cand.astype(np.uint8) * 255
    glyph = cv2.morphologyEx(glyph, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return cv2.morphologyEx(
        glyph,
        cv2.MORPH_OPEN,
        np.ones((cfg.morph_open_size, cfg.morph_open_size), np.uint8),
    )


def _template_match_score(cfg: MarkConfig, box_mask: Any, scale_base: int) -> float:
    cv2 = _cv2()
    sil = glyph_silhouette(cfg.asset_name)
    if sil is None or box_mask.size == 0:
        return 0.0
    gw = min(
        box_mask.shape[1] - 1, max(cfg.min_gw, int(cfg.alpha_width_frac * scale_base))
    )
    gh = min(box_mask.shape[0] - 1, max(4, int(cfg.alpha_height_frac * scale_base)))
    if gw < cfg.min_gw or gh < 4:
        return 0.0
    template = cv2.resize(sil, (gw, gh), interpolation=cv2.INTER_NEAREST)
    return float(cv2.matchTemplate(box_mask, template, cv2.TM_CCOEFF_NORMED).max())


def _residual_response(
    cfg: MarkConfig, image: Any, loc: tuple[int, int, int, int], absolute: bool
) -> Any:
    cv2, np = _cv2(), _np()
    x, y, bw, bh = loc
    if bh < 16 or bw < 16:
        return None
    roi = _to_bgr(image[y : y + bh, x : x + bw]).astype(np.float32)
    luma = roi.mean(axis=2)
    sat = roi.max(axis=2) - roi.min(axis=2)
    sigma = max(4.0, bh * 0.4)
    local_bg = cv2.GaussianBlur(luma, (0, 0), sigmaX=sigma, sigmaY=sigma)
    residual = luma - local_bg
    resp = (np.abs(residual) if absolute else np.clip(residual, 0, None)) * (
        sat < cfg.max_saturation
    )
    peak = float(resp.max())
    if peak <= 1e-6:
        return None
    return (resp / peak * 255).astype(np.uint8)


def _detect_response(
    cfg: MarkConfig, image: Any, loc: tuple[int, int, int, int]
) -> Any:
    cv2 = _cv2()
    if cfg.detect_frontend == "gray":
        x, y, bw, bh = loc
        if bh < 16 or bw < 16:
            return None
        return cv2.cvtColor(_to_bgr(image[y : y + bh, x : x + bw]), cv2.COLOR_BGR2GRAY)
    if cfg.detect_frontend == "contrast":
        return _residual_response(cfg, image, loc, True)
    if cfg.detect_frontend == "tophat":
        return _residual_response(cfg, image, loc, False)
    return None


def _ladder_best(
    cfg: MarkConfig, image: Any, loc: tuple[int, int, int, int]
) -> tuple[float, Any]:
    cv2 = _cv2()
    resp = _detect_response(cfg, image, loc)
    sil = glyph_silhouette(cfg.asset_name)
    if resp is None or sil is None:
        return 0.0, None
    base = _scale_base(cfg, image)
    best_score = 0.0
    best_box = None
    for scale in cfg.ladder:
        gw = max(cfg.min_gw, int(cfg.alpha_width_frac * base * scale))
        gh = max(4, int(cfg.alpha_height_frac * base * scale))
        if gw >= resp.shape[1] or gh >= resp.shape[0]:
            continue
        tmpl = cv2.resize(sil, (gw, gh), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(resp, tmpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, top_left = cv2.minMaxLoc(result)
        if score > best_score:
            tx, ty = int(top_left[0]), int(top_left[1])
            best_score = float(score)
            best_box = (tx, ty, tx + gw - 1, ty + gh - 1)
    return best_score, best_box


def _detect_text(cfg: MarkConfig, image: Any) -> Detection | None:
    if min(image.shape[:2]) < cfg.min_short_side:
        return None
    loc = _locate(cfg, image)
    x, y, bw, bh = loc
    box = _extract_mask(cfg, image, loc)
    coverage = float((box > 0).sum()) / float(max(1, bw * bh))
    base = _scale_base(cfg, image)
    match_box = None
    if cfg.detect_frontend == "binary":
        if coverage < 0.02:
            return None
        score = _template_match_score(cfg, box, base)
    else:
        score, match_box = _ladder_best(cfg, image, loc)
    if score < cfg.detect_ncc_threshold:
        return None
    fill_box = _footprint_rect(cfg, image, loc, box, match_box)
    return Detection(cfg.key, cfg.label, score, (x, y, bw, bh), fill_box)


def _footprint_rect(
    cfg: MarkConfig,
    image: Any,
    loc: tuple[int, int, int, int],
    box: Any,
    match_box: Any,
) -> tuple[int, int, int, int] | None:
    np = _np()
    x, y, bw, bh = loc
    h, w = image.shape[:2]
    ys, xs = np.where(box > 0)
    blob = (
        (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        if xs.size >= 20
        else None
    )
    rect = None
    if cfg.detect_frontend in ("gray", "contrast", "tophat") and match_box is not None:
        mx0, my0, mx1, my1 = match_box
        rect = (x + mx0, y + my0, x + mx1 + 1, y + my1 + 1)
    elif blob is not None:
        rect = (x + blob[0], y + blob[1], x + blob[2] + 1, y + blob[3] + 1)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    if cfg.key == "baidu":
        pad = max(4, int(0.15 * (y2 - y1)))
        return max(0, x1 - pad), max(0, y1 - pad), min(w, x + bw), min(h, y2 + 1 + pad)
    if cfg.key == "liblib":
        gh = y2 - y1 + 1
        pad = max(3, int(0.25 * gh))
        return (
            max(0, x1 - int(1.3 * gh)),
            max(0, y1 - pad),
            min(w, x2 + pad),
            min(h, y2 + 1 + pad),
        )
    pad = max(4, int(0.10 * (y2 - y1)))
    return max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + 1 + pad)


def mask_for(det: Detection, image: Any) -> Any:
    cv2, np = _cv2(), _np()
    height, width = image.shape[:2]
    if det.fill_box is not None:
        x1, y1, x2, y2 = det.fill_box
        if x1 >= x2 or y1 >= y2:
            return None
        mask = np.zeros((height, width), np.uint8)
        mask[y1:y2, x1:x2] = 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        return cv2.dilate(mask, kernel)
    scale = det.region[2]
    alpha = _gemini_interpolated_alpha(scale)
    placed = _footprint_indices(alpha, (det.region[0], det.region[1]), image.shape)
    if placed is None:
        return None
    a, (y1, y2, x1, x2) = placed
    silhouette = (a > _MASK_ALPHA).astype(np.uint8) * 255
    if not silhouette.any():
        return None
    mask = np.zeros((height, width), np.uint8)
    mask[y1:y2, x1:x2] = silhouette
    radius = max(13, int(scale * _MASK_DILATE_FRAC))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1)
    )
    return cv2.dilate(mask, kernel)


def _inpaint(image: Any, mask: Any) -> Any:
    cv2, np = _cv2(), _np()
    if image.ndim == 3 and image.shape[2] == 4:
        bgr = cv2.inpaint(image[:, :, :3], mask, 6, cv2.INPAINT_TELEA)
        return np.dstack([bgr, image[:, :, 3]])
    return cv2.inpaint(image, mask, 6, cv2.INPAINT_TELEA)


# sparkle detector


def _gemini_interpolated_alpha(size_px: int) -> Any:
    cv2 = _cv2()
    large = load_alpha(_GEMINI_LARGE)
    if large is None:
        return None
    if size_px == large.shape[1]:
        return large.copy()
    method = cv2.INTER_LINEAR if size_px > large.shape[1] else cv2.INTER_AREA
    return cv2.resize(large, (size_px, size_px), interpolation=method)


def _gemini_scan_scales(gray: Any, cache: dict[int, Any]) -> Any:
    cv2 = _cv2()
    height, width = gray.shape[:2]
    for side, template in cache.items():
        if side > height or side > width:
            continue
        response = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, maximum, _, max_location = cv2.minMaxLoc(response)
        yield side, float(maximum), max_location


def _gemini_template_cache() -> dict[int, Any]:
    cv2 = _cv2()
    large = load_alpha(_GEMINI_LARGE)
    return {
        side: cv2.resize(large, (side, side), interpolation=cv2.INTER_AREA)
        for side in _TEMPLATE_SCALES
    }


def _overlaps(
    candidate: tuple[int, int, int, float], prior: tuple[int, int, int, float]
) -> bool:
    radius = 0.5 * max(candidate[0], prior[0])
    return (
        abs(candidate[1] - prior[1]) < radius and abs(candidate[2] - prior[2]) < radius
    )


def _gemini_global_candidates(
    image: Any, cache: dict[int, Any]
) -> list[tuple[int, int, int, float]]:
    height, width = image.shape[:2]
    search_side = min(height, width, 512)
    origin_x, origin_y = width - search_side, height - search_side
    gray = _gray_float(image[origin_y:height, origin_x:width])
    ranked = sorted(
        (
            (
                score * min(1.0, (side / 96.0) ** 0.5),
                (side, origin_x + location[0], origin_y + location[1], score),
            )
            for side, score, location in _gemini_scan_scales(gray, cache)
        ),
        key=lambda item: (item[0], item[1][0], item[1][3], item[1][1], item[1][2]),
        reverse=True,
    )
    selected: list[tuple[int, int, int, float]] = []
    for _weighted, candidate in ranked:
        if any(_overlaps(candidate, prior) for prior in selected):
            continue
        selected.append(candidate)
        if len(selected) == _SELECT_TOPK:
            break
    return selected


def _gemini_grad_var(image: Any, scale: int, px: int, py: int) -> tuple[float, float]:
    cv2, np = _cv2(), _np()
    height, width = image.shape[:2]
    x2, y2 = min(width, px + scale), min(height, py + scale)
    region = image[py:y2, px:x2]
    gray = _gray_float(region)
    alpha = _gemini_interpolated_alpha(scale)[: y2 - py, : x2 - px]
    image_edges = cv2.magnitude(
        cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3),
        cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3),
    )
    alpha_edges = cv2.magnitude(
        cv2.Sobel(alpha, cv2.CV_32F, 1, 0, ksize=3),
        cv2.Sobel(alpha, cv2.CV_32F, 0, 1, ksize=3),
    )
    response = cv2.matchTemplate(image_edges, alpha_edges, cv2.TM_CCOEFF_NORMED)
    _, gradient, _, _ = cv2.minMaxLoc(response)
    variance = 0.0
    reference_height = min(py, scale)
    if reference_height > 8:
        reference = image[py - reference_height : py, px:x2]
        reference_gray = (
            cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
            if reference.ndim == 3
            else reference
        )
        _, region_std = cv2.meanStdDev((gray * 255.0).astype(np.uint8))
        _, reference_std = cv2.meanStdDev(reference_gray)
        if reference_std[0][0] > 5.0:
            variance = float(
                np.clip(1.0 - region_std[0][0] / reference_std[0][0], 0.0, 1.0)
            )
    return float(gradient), variance


def _gemini_corner_promote(
    image: Any, current_raw_ncc: float, cache: dict[int, Any]
) -> tuple[int, int, int, float] | None:
    height, width = image.shape[:2]
    desired = round(min(width, height) * _CORNER_PROMOTE_FRAC)
    side = min(
        min(width, height), max(_CORNER_PROMOTE_MIN, min(_CORNER_PROMOTE_MAX, desired))
    )
    origin_x, origin_y = width - side, height - side
    matches = _gemini_scan_scales(
        _gray_float(image[origin_y:height, origin_x:width]), cache
    )
    best, best_score = None, -1.0
    for side2, score, location in matches:
        if score > best_score:
            best_score, best = score, (side2, location)
    if (
        best is None
        or best_score < _CORNER_PROMOTE_NCC
        or best_score <= current_raw_ncc
    ):
        return None
    return best[0], origin_x + best[1][0], origin_y + best[1][1], float(best_score)


def _gemini_fused(image: Any, cand: tuple[int, int, int, float]) -> float:
    scale, px, py, spatial = cand
    if spatial < 0.25:
        return max(0.0, spatial * 0.5)
    gradient, variance = _gemini_grad_var(image, scale, px, py)
    return spatial * 0.50 + gradient * 0.30 + variance * 0.20


def _footprint_indices(
    alpha: Any, position: tuple[int, int], image_shape: tuple[int, ...]
) -> Any:
    x, y = position
    alpha_height, alpha_width = alpha.shape[:2]
    image_height, image_width = image_shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(image_width, x + alpha_width), min(image_height, y + alpha_height)
    if x1 >= x2 or y1 >= y2:
        return None
    alpha_x, alpha_y = x1 - x, y1 - y
    clipped = alpha[alpha_y : alpha_y + y2 - y1, alpha_x : alpha_x + x2 - x1]
    return clipped, (y1, y2, x1, x2)


def _gemini_core_and_bg(image: Any, alpha: Any, position: tuple[int, int]) -> Any:
    np = _np()
    placed = _footprint_indices(alpha, position, image.shape)
    if placed is None:
        return None
    a, (y1, y2, x1, x2) = placed
    peak = float(a.max())
    if peak < 0.2:
        return None
    core = a >= peak * _CORE_ALPHA_FRAC
    if not core.any():
        return None
    height, width = image.shape[:2]
    padding = int((x2 - x1) * 0.7)
    ry1, ry2 = max(0, y1 - padding), min(height, y2 + padding)
    rx1, rx2 = max(0, x1 - padding), min(width, x2 + padding)
    luminance = image[ry1:ry2, rx1:rx2].astype(np.float32).mean(axis=2)
    fy1, fy2, fx1, fx2 = y1 - ry1, y2 - ry1, x1 - rx1, x2 - rx1
    core_value = float(np.percentile(luminance[fy1:fy2, fx1:fx2][core], 75))
    background = np.ones(luminance.shape, dtype=bool)
    background[fy1:fy2, fx1:fx2] = False
    if background.sum() < 10:
        return None
    return core_value, float(np.median(luminance[background])), peak


def _gemini_core_saturation(
    image: Any, alpha: Any, position: tuple[int, int]
) -> float | None:
    np = _np()
    placed = _footprint_indices(alpha, position, image.shape)
    if placed is None:
        return None
    a, (y1, y2, x1, x2) = placed
    peak = float(a.max())
    if peak < 0.2:
        return None
    core = a >= peak * _CORE_ALPHA_FRAC
    if not core.any():
        return None
    pixels = image[y1:y2, x1:x2].astype(np.float32)[core]
    brightest = pixels.max(axis=1)
    darkest = pixels.min(axis=1)
    return float(np.median((brightest - darkest) / (brightest + 1.0)))


def detect_gemini(image: Any) -> Detection | None:
    if not available():
        return None
    source = _to_bgr(image)
    cache = _gemini_template_cache()
    candidates = _gemini_global_candidates(source, cache)
    raw = candidates[0][3] if candidates else -1.0
    promoted = _gemini_corner_promote(source, raw, cache)
    if promoted is not None:
        candidates.append(promoted)
    if not candidates:
        return None
    best, best_fused = candidates[0], _gemini_fused(source, candidates[0])
    for cand in candidates[1:]:
        fused = _gemini_fused(source, cand)
        if fused > best_fused:
            best_fused, best = fused, cand
    scale, px, py, spatial = best
    confidence = best_fused
    if spatial >= 0.25 and confidence < _FP_CONF:
        confidence = _gemini_fp_gate(source, best)
    if confidence < _GEMINI_TRUST_CONF:
        return None
    return Detection(
        "gemini", "Google Gemini sparkle", confidence, (px, py, scale, scale)
    )


def _gemini_fp_gate(image: Any, cand: tuple[int, int, int, float]) -> float:
    scale, px, py, _spatial = cand
    alpha = _gemini_interpolated_alpha(scale)
    position = (px, py)
    sample = _gemini_core_and_bg(image, alpha, position)
    margin = None if sample is None else sample[0] - sample[1]
    low_margin = margin is not None and margin < _FP_MARGIN
    gradient, _variance = _gemini_grad_var(image, scale, px, py)
    low_gradient = gradient < _FP_GRAD
    if not low_margin and not low_gradient:
        return _gemini_fused(image, cand)
    saturation = _gemini_core_saturation(image, alpha, position)
    neutral_core = (
        (not low_margin) and saturation is not None and saturation <= _WHITE_SAT
    )
    if confidence_above_keep(image, cand) and neutral_core:
        return _gemini_fused(image, cand)
    return min(_gemini_fused(image, cand), 0.30)


def confidence_above_keep(image: Any, cand: tuple[int, int, int, float]) -> bool:
    return _gemini_fused(image, cand) >= _KEEP_CONF
