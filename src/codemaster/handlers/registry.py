from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarkSpec:
    name: str
    corner: str
    fraction: float = 0.14

    def box(self, width: int, height: int) -> tuple[int, int, int, int]:
        rx = max(1, int(width * self.fraction))
        ry = max(1, int(height * self.fraction))
        if self.corner == "bl":
            return 0, height - ry, rx, height
        if self.corner == "tr":
            return width - rx, 0, width, ry
        if self.corner == "tl":
            return 0, 0, rx, ry
        return width - rx, height - ry, width, height

    def locate(self, image: Any, width: int, height: int) -> bool:
        region = image.crop(self.box(width, height)).convert("L")
        values = [int(byte) for byte in region.tobytes()]
        if not values:
            return False
        probe = image.convert("L").resize((min(32, width), min(32, height)))
        whole = [int(byte) for byte in probe.tobytes()]
        region_mean = sum(values) / len(values)
        whole_mean = sum(whole) / len(whole)
        return abs(region_mean - whole_mean) > 24


MARKS: tuple[MarkSpec, ...] = (
    MarkSpec("corner-label", "br"),
    MarkSpec("corner-label", "bl"),
)


def fill(image: Any, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    ratio = 16
    small = image.resize((max(1, image.width // ratio), max(1, image.height // ratio)))
    smooth = small.resize(image.size, 2)
    region = smooth.crop((left, top, right, bottom))
    image.paste(region, (left, top))
