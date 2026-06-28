"""Minimal pure-python RS-274X Gerber and Excellon drill parsers.

This module intentionally has NO external dependencies (no gerbv / FlatCAM).
It extracts enough geometry to drive a first functional cut of PCB isolation,
drilling and cutout G-code generation.

Supported (functional first cut):
- RS-274X format spec (%FSLAX..Y..*%) and units (%MOMM*% / %MOIN*%).
- Aperture definitions (%ADD..*%) for circles (C) and rectangles (R).
- Aperture selection (Dnn where nn >= 10).
- Linear interpolation (G01) and the operations D01 (draw), D02 (move),
  D03 (flash). Flashes become pads; draws become trace segments.
- Excellon drill files: tool definitions (Tnn C<dia>) and drill hits.

Assumptions / limitations (documented TODOs below in code):
- TODO: arcs G02/G03 are NOT interpolated; a G02/G03 draw is approximated as a
  straight segment between current point and target. Good enough for a first cut.
- TODO: region fills (G36/G37) are captured only as their outline polyline; the
  fill itself is not rasterised.
- TODO: aperture macros (%AM*%), polygons (P), obround (O) and step-and-repeat
  (%SR*%) are not supported and are ignored.
- TODO: Excellon routed slots (G00/G01 with M15/M16) are not supported; only
  point drill hits are emitted.

All coordinates returned are in millimetres.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


INCH_TO_MM = 25.4


@dataclass
class Aperture:
    """A Gerber aperture (tool shape)."""

    code: int
    shape: str  # "C" circle, "R" rectangle, or "?" unknown
    # For circles: (diameter,). For rectangles: (width, height). In millimetres.
    params: tuple[float, ...] = ()

    @property
    def diameter_mm(self) -> float:
        """Best-effort nominal diameter / largest dimension in mm."""
        if not self.params:
            return 0.0
        return max(self.params)


@dataclass
class Segment:
    """A straight trace segment drawn with a given aperture, in mm."""

    start: tuple[float, float]
    end: tuple[float, float]
    aperture: int  # aperture code, or 0 if unknown
    width_mm: float = 0.0


@dataclass
class Pad:
    """A flashed pad, in mm."""

    position: tuple[float, float]
    aperture: int
    shape: str  # "C" or "R" or "?"
    size_mm: tuple[float, ...] = ()


@dataclass
class GerberData:
    """Parsed copper geometry, all coordinates in millimetres."""

    units_mm: bool = True
    segments: list[Segment] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)
    apertures: dict[int, Aperture] = field(default_factory=dict)
    regions: list[list[tuple[float, float]]] = field(default_factory=list)

    @property
    def bounds_mm(self) -> tuple[float, float, float, float] | None:
        """(min_x, min_y, max_x, max_y) over all geometry, or None if empty."""
        xs: list[float] = []
        ys: list[float] = []
        for seg in self.segments:
            xs.extend((seg.start[0], seg.end[0]))
            ys.extend((seg.start[1], seg.end[1]))
        for pad in self.pads:
            xs.append(pad.position[0])
            ys.append(pad.position[1])
        for region in self.regions:
            for x, y in region:
                xs.append(x)
                ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class DrillHit:
    """A single drilled point, in mm."""

    position: tuple[float, float]
    diameter_mm: float
    tool: int


@dataclass
class ExcellonData:
    """Parsed drill data, all coordinates in millimetres."""

    units_mm: bool = True
    tools: dict[int, float] = field(default_factory=dict)  # tool number -> diameter mm
    hits: list[DrillHit] = field(default_factory=list)

    @property
    def bounds_mm(self) -> tuple[float, float, float, float] | None:
        if not self.hits:
            return None
        xs = [h.position[0] for h in self.hits]
        ys = [h.position[1] for h in self.hits]
        return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------- #
# RS-274X Gerber parser
# --------------------------------------------------------------------------- #

_FS_RE = re.compile(r"FSLAX(\d)(\d)Y(\d)(\d)", re.IGNORECASE)
_AD_RE = re.compile(r"ADD(\d+)([A-Za-z]+)[,]?([0-9.X]*)", re.IGNORECASE)
_COORD_RE = re.compile(r"([XYIJ])([+-]?\d+)")


@dataclass
class _FormatSpec:
    """Gerber coordinate format: integer + decimal digit counts."""

    x_int: int = 2
    x_dec: int = 4
    y_int: int = 2
    y_dec: int = 4
    leading_zero_omitted: bool = True  # "L" mode (most common)


def _decode_coord(token: str, dec_digits: int, leading_omitted: bool) -> float:
    """Decode a raw Gerber/Excellon integer coordinate token into a float.

    With leading-zero suppression the value is right-justified by the decimal
    count; an explicit decimal point in the token is honoured directly.
    """
    if "." in token:
        return float(token)
    negative = token.startswith("-")
    digits = token.lstrip("+-")
    if not digits:
        return 0.0
    if leading_omitted:
        value = int(digits) / (10 ** dec_digits)
    else:
        # Trailing-zero suppression: pad on the right. Rare; best-effort.
        value = int(digits) / (10 ** dec_digits)
    return -value if negative else value


def parse_gerber(text: str) -> GerberData:
    """Parse RS-274X Gerber text into :class:`GerberData` (mm)."""
    data = GerberData()
    fmt = _FormatSpec()
    units_mm = True
    to_mm = 1.0

    cur_x = 0.0
    cur_y = 0.0
    cur_aperture = 0
    interpolate = True  # G01 linear (we only support linear)
    in_region = False
    region_pts: list[tuple[float, float]] = []

    # Split on '*' which terminates every Gerber data block; '%' wraps params.
    blocks = re.split(r"[*]", text.replace("\n", "").replace("\r", ""))

    for raw in blocks:
        block = raw.strip().strip("%").strip()
        if not block:
            continue
        upper = block.upper()

        # ---- Parameter blocks ------------------------------------------- #
        if upper.startswith("MO"):
            units_mm = "MM" in upper
            to_mm = 1.0 if units_mm else INCH_TO_MM
            data.units_mm = units_mm
            continue
        if upper.startswith("FS"):
            m = _FS_RE.search(upper)
            if m:
                fmt = _FormatSpec(
                    x_int=int(m.group(1)),
                    x_dec=int(m.group(2)),
                    y_int=int(m.group(3)),
                    y_dec=int(m.group(4)),
                    leading_zero_omitted="L" in upper.split("X")[0],
                )
            continue
        if upper.startswith("AD"):
            m = _AD_RE.search(block)
            if m:
                code = int(m.group(1))
                shape = m.group(2).upper()
                raw_params = [p for p in m.group(3).split("X") if p]
                try:
                    params = tuple(float(p) * to_mm for p in raw_params)
                except ValueError:
                    params = ()
                norm = "C" if shape.startswith("C") else "R" if shape.startswith("R") else "?"
                data.apertures[code] = Aperture(code=code, shape=norm, params=params)
            continue
        if upper.startswith("AM") or upper.startswith("SR") or upper.startswith("LP"):
            # TODO: aperture macros / step-repeat / layer polarity unsupported.
            continue

        # ---- Function / data blocks ------------------------------------- #
        # Region mode toggles.
        if "G36" in upper:
            in_region = True
            region_pts = []
            continue
        if "G37" in upper:
            in_region = False
            if len(region_pts) >= 2:
                data.regions.append(region_pts)
            region_pts = []
            continue
        if "G01" in upper:
            interpolate = True
        if "G02" in upper or "G03" in upper:
            # TODO: arc interpolation. Approximated as straight segment.
            interpolate = True

        # Aperture selection: a bare Dnn with nn >= 10.
        dsel = re.search(r"D(\d+)", upper)
        op = None
        if dsel:
            dnum = int(dsel.group(1))
            if dnum >= 10:
                cur_aperture = dnum
            elif dnum in (1, 2, 3):
                op = dnum

        # Coordinates present?
        coords = dict(_COORD_RE.findall(block))
        if not coords and op is None:
            continue

        new_x = cur_x
        new_y = cur_y
        if "X" in coords:
            new_x = _decode_coord(coords["X"], fmt.x_dec, fmt.leading_zero_omitted) * to_mm
        if "Y" in coords:
            new_y = _decode_coord(coords["Y"], fmt.y_dec, fmt.leading_zero_omitted) * to_mm

        if op == 1:  # D01 draw
            if in_region:
                if not region_pts:
                    region_pts.append((cur_x, cur_y))
                region_pts.append((new_x, new_y))
            elif interpolate:
                ap = data.apertures.get(cur_aperture)
                width = ap.diameter_mm if ap else 0.0
                data.segments.append(
                    Segment((cur_x, cur_y), (new_x, new_y), cur_aperture, width)
                )
            cur_x, cur_y = new_x, new_y
        elif op == 2:  # D02 move
            if in_region:
                if region_pts and len(region_pts) >= 2:
                    data.regions.append(region_pts)
                region_pts = [(new_x, new_y)]
            cur_x, cur_y = new_x, new_y
        elif op == 3:  # D03 flash -> pad
            ap = data.apertures.get(cur_aperture)
            data.pads.append(
                Pad(
                    position=(new_x, new_y),
                    aperture=cur_aperture,
                    shape=ap.shape if ap else "?",
                    size_mm=ap.params if ap else (),
                )
            )
            cur_x, cur_y = new_x, new_y
        else:
            # Bare coordinate move without explicit op: treat as a move.
            cur_x, cur_y = new_x, new_y

    return data


# --------------------------------------------------------------------------- #
# Excellon drill parser
# --------------------------------------------------------------------------- #

_TOOL_DEF_RE = re.compile(r"^T(\d+)C([0-9.]+)", re.IGNORECASE)
_TOOL_SEL_RE = re.compile(r"^T(\d+)\s*$", re.IGNORECASE)
_DRILL_COORD_RE = re.compile(r"([XY])([+-]?\d*\.?\d+)")


def parse_excellon(text: str) -> ExcellonData:
    """Parse an Excellon drill file into :class:`ExcellonData` (mm)."""
    data = ExcellonData()
    units_mm = True
    to_mm = 1.0
    dec_digits = 4
    leading_omitted = True
    cur_tool = 0
    in_header = True

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        upper = line.upper()

        if upper in ("M48",):
            in_header = True
            continue
        if upper in ("%", "M95"):
            in_header = False
            continue
        if upper.startswith("METRIC"):
            units_mm = True
            to_mm = 1.0
            data.units_mm = True
            if "TZ" in upper:
                leading_omitted = False
            continue
        if upper.startswith("INCH"):
            units_mm = False
            to_mm = INCH_TO_MM
            data.units_mm = False
            dec_digits = 4
            if "TZ" in upper:
                leading_omitted = False
            continue
        if upper.startswith("M71"):  # metric
            units_mm = True
            to_mm = 1.0
            data.units_mm = True
            continue
        if upper.startswith("M72"):  # inch
            units_mm = False
            to_mm = INCH_TO_MM
            data.units_mm = False
            continue

        # Tool definition (T01C0.8) — may appear in header.
        m = _TOOL_DEF_RE.match(line)
        if m:
            tool = int(m.group(1))
            dia = float(m.group(2)) * to_mm
            data.tools[tool] = dia
            continue

        # Tool selection (T01) in the body.
        m = _TOOL_SEL_RE.match(line)
        if m:
            cur_tool = int(m.group(1))
            in_header = False
            continue

        if in_header:
            continue

        if upper in ("M30", "M00", "M01"):
            break

        # Drill hit coordinates.
        coords = dict(_DRILL_COORD_RE.findall(line))
        if coords and ("X" in coords or "Y" in coords):
            x = _decode_coord(coords.get("X", "0"), dec_digits, leading_omitted) * to_mm
            y = _decode_coord(coords.get("Y", "0"), dec_digits, leading_omitted) * to_mm
            dia = data.tools.get(cur_tool, 0.0)
            data.hits.append(DrillHit((x, y), dia, cur_tool))

    return data


def parse_gerber_file(path: Path) -> GerberData:
    return parse_gerber(Path(path).read_text())


def parse_excellon_file(path: Path) -> ExcellonData:
    return parse_excellon(Path(path).read_text())
