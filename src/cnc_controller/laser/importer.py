from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..gcode import analyze_gcode_lines
from .domain import LaserJob, LaserLayer, LaserOperationType
from .rayforge_adapter import RayforgeAdapter, RayforgeUnavailable


GCODE_EXTENSIONS = {".gcode", ".gc", ".nc", ".tap"}
VECTOR_EXTENSIONS = {".svg", ".dxf", ".pdf"}
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
SUPPORTED_EXTENSIONS = GCODE_EXTENSIONS | VECTOR_EXTENSIONS | RASTER_EXTENSIONS

_SVG_NUMBER = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


def import_laser_file(path: Path, adapter: RayforgeAdapter | None = None) -> LaserJob:
    path = Path(path)
    suffix = path.suffix.casefold()
    if not path.is_file():
        raise ValueError(f"File not found: {path}")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported laser file: {path.suffix or '(no extension)'}")
    if suffix in GCODE_EXTENSIONS:
        return _import_gcode(path)

    adapter = adapter or RayforgeAdapter()
    try:
        scan = adapter.scan(path)
        layers = [
            LaserLayer(
                name=item["name"] or f"Layer {index + 1}",
                color=item["color"],
                operation=(
                    LaserOperationType.RASTER
                    if suffix in RASTER_EXTENSIONS
                    else LaserOperationType.LINE
                ),
                enabled=item["enabled"],
                feature_count=item["feature_count"],
            )
            for index, item in enumerate(scan.layers)
        ]
        if not layers:
            layers = [_default_layer(path, suffix)]
        size = scan.natural_size_mm
        return LaserJob(
            path,
            suffix.lstrip("."),
            layers=layers,
            natural_size_mm=size,
            bounds_mm=(0.0, 0.0, size[0], size[1]) if size else None,
            warnings=scan.warnings,
            errors=scan.errors,
        )
    except RayforgeUnavailable as exc:
        # SVG metadata is still useful for touchscreen setup/preview.  The
        # explicit warning prevents users from mistaking this for generated
        # machine code.
        size, layers, errors = _fallback_metadata(path, suffix)
        return LaserJob(
            path,
            suffix.lstrip("."),
            layers=layers or [_default_layer(path, suffix)],
            natural_size_mm=size,
            bounds_mm=(0.0, 0.0, size[0], size[1]) if size else None,
            warnings=[str(exc)],
            errors=errors,
        )


def _import_gcode(path: Path) -> LaserJob:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("G-code must be an ASCII/UTF-8 text file.") from exc
    analysis = analyze_gcode_lines(lines)
    errors = [] if analysis.motion_line_count else ["No XY motion was found in this G-code."]
    warnings = []
    if not analysis.uses_units_mm:
        warnings.append("G20 inch-mode commands detected; bounds are not converted automatically.")
    return LaserJob(
        source_path=path,
        source_kind="gcode",
        layers=[
            LaserLayer(
                name="Imported G-code",
                operation=LaserOperationType.LINE,
                speed_mm_min=analysis.max_feed_mm_min or 500.0,
                power_percent=float(analysis.max_power_s or 0) / 10.0,
            )
        ],
        bounds_mm=analysis.bounds_mm,
        warnings=warnings,
        errors=errors,
        gcode_lines=lines,
    )


def _fallback_metadata(
    path: Path, suffix: str
) -> tuple[tuple[float, float] | None, list[LaserLayer], list[str]]:
    if suffix != ".svg":
        return None, [], []
    try:
        root = ET.fromstring(path.read_bytes())
    except ET.ParseError as exc:
        return None, [], [f"Invalid SVG: {exc}"]

    size = _svg_size(root)
    seen: set[str] = set()
    layers: list[LaserLayer] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}:
            continue
        style = element.attrib.get("style", "")
        stroke = element.attrib.get("stroke") or _style_value(style, "stroke") or "#1577d4"
        name = element.attrib.get("{http://www.inkscape.org/namespaces/inkscape}label")
        name = name or element.attrib.get("id") or stroke
        key = f"{name}:{stroke}"
        if key in seen:
            continue
        seen.add(key)
        layers.append(LaserLayer(name=name, color=stroke if stroke.startswith("#") else "#1577d4"))
    return size, layers, []


def _svg_size(root: ET.Element) -> tuple[float, float] | None:
    viewbox = root.attrib.get("viewBox", "").replace(",", " ").split()
    if len(viewbox) == 4:
        try:
            return float(viewbox[2]), float(viewbox[3])
        except ValueError:
            pass
    width = _dimension(root.attrib.get("width"))
    height = _dimension(root.attrib.get("height"))
    return (width, height) if width and height else None


def _dimension(raw: str | None) -> float | None:
    if not raw:
        return None
    match = _SVG_NUMBER.match(raw)
    if not match:
        return None
    value = float(match.group(1))
    if raw.strip().lower().endswith("in"):
        value *= 25.4
    elif raw.strip().lower().endswith("px"):
        value *= 25.4 / 96.0
    return value


def _style_value(style: str, key: str) -> str | None:
    for item in style.split(";"):
        name, separator, value = item.partition(":")
        if separator and name.strip() == key:
            return value.strip()
    return None


def _default_layer(path: Path, suffix: str) -> LaserLayer:
    operation = LaserOperationType.RASTER if suffix in RASTER_EXTENSIONS else LaserOperationType.LINE
    return LaserLayer(path.stem, operation=operation)
