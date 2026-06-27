from __future__ import annotations

from pathlib import Path


def simple_vector_gcode(source: Path, feed_mm_min: float, power_s: int, passes: int = 1) -> list[str]:
    """Placeholder vector pipeline entry point.

    Full SVG/DXF support will be implemented by adapting Rayforge-style import
    and path planning. For now this produces a safe header/footer and records
    the source file so the UI workflow can be exercised on the Raspberry Pi.
    """
    return [
        f"(source: {source.name})",
        "G21",
        "G90",
        f"F{feed_mm_min:.0f}",
        f"S{power_s}",
        f"(passes: {passes})",
        "M5",
    ]
