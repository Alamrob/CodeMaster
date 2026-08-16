from __future__ import annotations

import random

import pytest

from codemaster.handlers import image_meta as im
from test_gif import _gif_with_meta
from test_platform import _jpeg_with_meta, _png_with_text
from test_tiff import _real_tiff
from test_webp import _webp_with_c2pa


def _png_plain() -> bytes:
    return _png_with_text()


def _jpeg_plain() -> bytes:
    return _jpeg_with_meta()


_SAMPLES: dict[str, list[bytes]] = {
    "webp": [_webp_with_c2pa()],
    "gif": [_gif_with_meta()],
    "tiff": [_real_tiff()],
    "png": [_png_plain()],
    "jpeg": [_jpeg_plain()],
}


def _mutations(data: bytes) -> list[bytes]:
    mutated: list[bytes] = []
    for cut in (0, 1, 2, 4, 8, 16, 64, len(data) - 1, len(data) // 2):
        if 0 <= cut <= len(data):
            mutated.append(data[:cut])
    for pos in (0, 1, 2, 4, 8, 16, len(data) // 2, len(data) - 1):
        if 0 <= pos < len(data):
            flipped = bytearray(data)
            flipped[pos] ^= 0xFF
            mutated.append(bytes(flipped))
    for pos in (2, 6, 10, 14, 20):
        if pos + 4 <= len(data):
            corrupted = bytearray(data)
            corrupted[pos : pos + 4] = b"\xff\xff\xff\xff"
            mutated.append(bytes(corrupted))
    if data:
        mutated.append(bytes(len(data)))
    return mutated


def test_walkers_never_raise_on_mutations() -> None:
    rnd = random.Random(0xC0DE)
    for kind, samples in _SAMPLES.items():
        for base in samples:
            bunch = _mutations(base) + [
                bytes(rnd.randrange(256) for _ in range(rnd.randrange(0, 64)))
                for _ in range(8)
            ]
            for data in bunch:
                _audit_wash(kind, data)


def _audit_wash(kind: str, data: bytes) -> None:
    if kind == "jpeg":
        im._jpeg_audit(data)
        im._jpeg_wash(data)
    elif kind == "png":
        im._png_audit(data)
        im._png_wash(data)
    elif kind == "webp":
        im._riff_audit(data)
        im._riff_wash(data)
    elif kind == "gif":
        im._gif_audit(data)
        im._gif_wash(data)
    elif kind == "tiff":
        im._tiff_audit(data)
        im._tiff_wash(data)


@pytest.mark.parametrize("kind", list(_SAMPLES))
def test_truncated_and_poisoned_headers_are_safe(kind: str) -> None:
    for sample in _SAMPLES[kind]:
        for data in (sample[:1], b"", sample[:0], sample[:3]):
            _audit_wash(kind, data)


def test_malformed_length_prefix_never_crashes() -> None:
    from test_webp import _riff_chunk

    boom_c2pa = _riff_chunk(b"C2PA", b"jumb")[:6]
    body = _riff_chunk(b"VP8L", b"\x2f\x00\x00\x00" + b"\x00" * 20)
    data = b"RIFF" + b"\xff\xff\xff\x7f" + b"WEBP" + body + boom_c2pa
    im._riff_audit(data)
    im._riff_wash(data)
