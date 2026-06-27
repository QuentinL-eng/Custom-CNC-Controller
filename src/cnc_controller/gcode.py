from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_WORD_RE = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))", re.IGNORECASE)
_COMMENT_PARENS_RE = re.compile(r"\([^)]*\)")


@dataclass(frozen=True)
class GcodeAnalysis:
    line_count: int
    motion_line_count: int
    bounds_mm: tuple[float, float, float, float] | None
    max_feed_mm_min: float | None
    max_power_s: int | None
    uses_units_mm: bool
    uses_absolute_positioning: bool


def strip_comments(line: str) -> str:
    without_parens = _COMMENT_PARENS_RE.sub("", line)
    return without_parens.split(";", 1)[0].strip()


def parse_words(line: str) -> dict[str, float]:
    return {letter.upper(): float(value) for letter, value in _WORD_RE.findall(strip_comments(line))}


def analyze_gcode_lines(lines: list[str]) -> GcodeAnalysis:
    x = y = 0.0
    absolute = True
    units_mm = True
    min_x = min_y = max_x = max_y = None
    motion_lines = 0
    max_feed = None
    max_power = None

    for raw in lines:
        words = parse_words(raw)
        if not words:
            continue
        g = int(words["G"]) if "G" in words else None
        if g == 20:
            units_mm = False
        elif g == 21:
            units_mm = True
        elif g == 90:
            absolute = True
        elif g == 91:
            absolute = False

        if "F" in words:
            max_feed = words["F"] if max_feed is None else max(max_feed, words["F"])
        if "S" in words:
            candidate = int(round(words["S"]))
            max_power = candidate if max_power is None else max(max_power, candidate)

        if g in {0, 1, 2, 3} and ("X" in words or "Y" in words):
            motion_lines += 1
            next_x = words.get("X", x)
            next_y = words.get("Y", y)
            if not absolute:
                next_x = x + words.get("X", 0.0)
                next_y = y + words.get("Y", 0.0)
            x, y = next_x, next_y
            min_x = x if min_x is None else min(min_x, x)
            min_y = y if min_y is None else min(min_y, y)
            max_x = x if max_x is None else max(max_x, x)
            max_y = y if max_y is None else max(max_y, y)

    bounds = None if min_x is None else (min_x, min_y, max_x, max_y)
    return GcodeAnalysis(len(lines), motion_lines, bounds, max_feed, max_power, units_mm, absolute)


def analyze_gcode_file(path: Path) -> GcodeAnalysis:
    return analyze_gcode_lines(path.read_text().splitlines())
