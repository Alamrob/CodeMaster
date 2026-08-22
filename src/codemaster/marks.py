from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MARKS_TOML = Path(__file__).with_name("marks.toml")


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
    ladder: tuple[float, ...] = field(default_factory=lambda: (1.0,))
    alpha_width_frac: float = 0.1
    alpha_height_frac: float = 0.03
    min_gw: int = 8
    min_short_side: int = 200


def load(path: Path | None = None) -> tuple[MarkConfig, ...]:
    source = path if path is not None else _MARKS_TOML
    with source.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    marks: list[MarkConfig] = []
    for entry in data.get("marks", []):
        marks.append(
            MarkConfig(
                key=str(entry["key"]),
                label=str(entry.get("label", entry["key"])),
                asset_name=str(entry["asset"]),
                corner=str(entry.get("corner", "br")),
                margin_floor=int(entry.get("margin_floor", 4)),
                width_frac=float(entry.get("width_frac", 0.2)),
                height_frac=float(entry.get("height_frac", 0.06)),
                margin_x_frac=float(entry.get("margin_x_frac", 0.0)),
                margin_bottom_frac=float(entry.get("margin_bottom_frac", 0.0)),
                max_saturation=int(entry.get("max_saturation", 55)),
                logo_min_luma=int(entry.get("logo_min_luma", 150)),
                tophat_delta=int(entry.get("tophat_delta", 12)),
                morph_open_size=int(entry.get("morph_open_size", 5)),
                detect_ncc_threshold=float(entry.get("detect_ncc_threshold", 0.4)),
                detect_frontend=str(entry.get("detect_frontend", "tophat")),
                scale_basis=str(entry.get("scale_basis", "short")),
                ladder=tuple(float(v) for v in entry.get("ladder", [1.0])),
                alpha_width_frac=float(entry.get("alpha_width_frac", 0.1)),
                alpha_height_frac=float(entry.get("alpha_height_frac", 0.03)),
                min_gw=int(entry.get("min_gw", 8)),
                min_short_side=int(entry.get("min_short_side", 200)),
            )
        )
    return tuple(marks)


REGISTRY = load()
