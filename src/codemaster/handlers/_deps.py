from __future__ import annotations

import importlib
from typing import Any

_LOADED: dict[str, Any] = {}


def load(name: str) -> Any:
    mod = _LOADED.get(name)
    if mod is None:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            mod = False
        _LOADED[name] = mod
    return mod


def pillow_ok() -> bool:
    return bool(load("PIL"))


def opencv_ok() -> bool:
    return bool(load("cv2"))


def piexif_ok() -> bool:
    return bool(load("piexif"))


def c2pa_ok() -> bool:
    return bool(load("c2pa"))
