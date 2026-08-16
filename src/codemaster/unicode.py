from __future__ import annotations

import unicodedata

from codemaster.fsutil import line_starts, offset_line_col
from codemaster.report import Grade, Slip

STEALTH = frozenset(
    {
        0x00AD,
        0x034F,
        0x061C,
        0x180B,
        0x180C,
        0x180D,
        0x180E,
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2060,
        0x2061,
        0x2062,
        0x2063,
        0x2064,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
        0xFEFF,
    }
)


def probe(text: str) -> list[Slip]:
    starts = line_starts(text)
    found: list[Slip] = []
    seen: set[tuple[int, int]] = set()
    for index, char in enumerate(text):
        point = ord(char)
        if point in STEALTH:
            line, col = offset_line_col(text, index, starts)
            key = (line, point)
            if key in seen:
                continue
            seen.add(key)
            found.append(Slip(line, col, "stealth", f"U+{point:04X}", Grade.DANGER))
        elif point >= 0x80:
            category = unicodedata.category(char)
            if category in ("Cf", "Co"):
                line, col = offset_line_col(text, index, starts)
                found.append(
                    Slip(
                        line, col, "foreign", f"U+{point:04X} {category}", Grade.SIGNAL
                    )
                )
    return found


def flush(text: str) -> str:
    return "".join(char for char in text if ord(char) not in STEALTH)


def stealth_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    anchor: int | None = None
    for index, char in enumerate(text):
        inside = ord(char) in STEALTH
        if inside and anchor is None:
            anchor = index
        elif not inside and anchor is not None:
            ranges.append((anchor, index))
            anchor = None
    if anchor is not None:
        ranges.append((anchor, len(text)))
    return ranges
