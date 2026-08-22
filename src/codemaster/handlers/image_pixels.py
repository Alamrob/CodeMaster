from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from codemaster.handlers import _deps, registry, visible
from codemaster.handlers.base import Blob, Handler
from codemaster.report import Grade, Slip
from codemaster.scrubber import Edits


class _PixelHandler:
    name = "pixels"

    def probe(self, blob: Blob) -> bool:
        return blob.kind == "image" and _deps.pillow_ok()

    def audit(self, blob: Blob) -> list[Slip]:
        slips: list[Slip] = []
        image = _open(blob)
        if image is not None:
            width, height = image.size
            for mark in registry.MARKS:
                if mark.locate(image, width, height):
                    slips.append(Slip(1, 1, "mark", mark.name, Grade.SIGNAL))
            stego = _lsb_stego_score(image)
            if stego is not None and stego > 0.08:
                slips.append(
                    Slip(
                        1,
                        1,
                        "stego",
                        f"LSB data embedding {stego:.2f}",
                        Grade.SIGNAL,
                    )
                )
        if _deps.opencv_ok():
            cv_img = _decode_cv(blob)
            if cv_img is not None:
                for det in visible.detect_all(cv_img):
                    slips.append(
                        Slip(
                            1,
                            1,
                            "mark",
                            f"{det.label} ({det.confidence:.2f})",
                            Grade.DANGER,
                        )
                    )
        return slips

    def wash(self, blob: Blob, edits: Edits) -> tuple[bytes, list[str]]:
        if _deps.opencv_ok():
            cv_img = _decode_cv(blob)
            if cv_img is not None:
                cv_out, found = visible.remove_marks(cv_img)
                if found:
                    return _encode_cv(cv_out, blob.path.suffix), found
        image = _open(blob)
        if image is None:
            return blob.data, []
        width, height = image.size
        boxes = [
            mark.box(width, height)
            for mark in registry.MARKS
            if mark.locate(image, width, height)
        ]
        if not boxes:
            return blob.data, []
        for box in boxes:
            registry.fill(image, box)
        output = io.BytesIO()
        image.save(output, format=image.format or "PNG")
        return output.getvalue(), ["marks"]


HANDLER: Handler = _PixelHandler()


def _open(blob: Blob) -> Any:
    image_mod = _deps.load("PIL.Image")
    if not image_mod:
        return None
    try:
        image = image_mod.open(io.BytesIO(blob.data))
        image.load()
        return image
    except Exception:
        return None


def _lsb_stego_score(image: Any) -> float | None:
    """Heuristic score for LSB data embedding in the least-significant bit.

    Measures per-channel pairwise correlation of LSB bits across a sampling
    grid of pixel pairs. Natural images have locally correlated LSBs; data
    steganography randomizes them, pushing the score toward ``1.0``. Returns
    ``None`` when the image cannot be sampled (too small or unsupported mode).
    """
    np = _deps.load("numpy")
    if not np:
        return None
    try:
        gray = image.convert("L")
        arr = np.asarray(gray, dtype=np.uint8)
    except Exception:
        return None
    height, width = arr.shape
    if height < 64 or width < 64:
        return None
    step = max(2, min(width, height) // 64)
    ys = range(16, height - 16, step)
    xs = range(16, width - 16, step)
    samples = 0
    equal = 0
    for y in ys:
        for x in xs:
            lsb_a = int(arr[y, x]) & 1
            lsb_b = int(arr[y, x + 1]) & 1
            samples += 1
            if lsb_a == lsb_b:
                equal += 1
    if samples == 0:
        return None
    return 1.0 - equal / samples


def _decode_cv(blob: Blob) -> Any:
    cv2, np = _deps.load("cv2"), _deps.load("numpy")
    if not cv2 or not np:
        return None
    try:
        arr = np.frombuffer(blob.data, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None


def _encode_cv(image: Any, suffix: str) -> bytes:
    cv2 = _deps.load("cv2")
    ext = Path(suffix).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return bytes(
            cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
        )
    if ext == ".webp":
        return bytes(cv2.imencode(".webp", image)[1].tobytes())
    return bytes(cv2.imencode(".png", image)[1].tobytes())
