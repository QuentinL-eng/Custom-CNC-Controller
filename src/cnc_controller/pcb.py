"""PCB isolation / drill / cutout G-code generation (first functional cut).

Pure-python, no external deps. Geometry is parsed by :mod:`cnc_controller.gerber`
and turned into ordered :class:`PcbStage` jobs by :func:`generate_pcb_jobs`.

Coordinate convention: all stages share the same X/Y work origin (the user
probes/zeroes XY once on the board). Only Z is re-probed after a tool change,
hence ``requires_probe_z`` on the stages that follow a tool swap.

The generation is deliberately simple and conservative:
- Isolation: a single offset pass. Each copper segment / pad outline / region
  outline is engraved at ``ISOLATION_DEPTH_MM``. (TODO: true polygon offset and
  multi-pass clearing; we currently engrave along/around geometry rather than
  computing an exact tool-radius offset of filled copper.)
- Drilling: simple peck cycle per hole, grouped by tool diameter, with a tool
  change + Z re-probe between diameter groups.
- Cutout: tabbed perimeter cut from the cutout outline if provided, else the
  bounding rectangle of the copper layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gerber import (
    GerberData,
    parse_excellon_file,
    parse_gerber_file,
)
from .models import MachineProfile


# --------------------------------------------------------------------------- #
# Tunable constants (sensible defaults; override via generate_pcb_jobs args).
# --------------------------------------------------------------------------- #
ISOLATION_TOOL_DIAMETER_MM = 0.2   # V-bit / engraving tool nominal width
ISOLATION_DEPTH_MM = -0.10         # copper depth below probed Z=0
ISOLATION_FEED_MM_MIN = 120.0
ISOLATION_PLUNGE_MM_MIN = 60.0

DRILL_DEPTH_MM = -1.8              # through 1.6mm board + breakout
DRILL_PECK_MM = 0.6
DRILL_FEED_MM_MIN = 80.0

CUTOUT_DEPTH_MM = -2.0
CUTOUT_FEED_MM_MIN = 150.0
CUTOUT_PLUNGE_MM_MIN = 60.0
CUTOUT_PASS_DEPTH_MM = 0.5         # depth removed per perimeter pass
CUTOUT_TAB_COUNT = 4
CUTOUT_TAB_HEIGHT_MM = 0.6         # leave this much material at each tab
CUTOUT_TAB_WIDTH_MM = 3.0

DEFAULT_SAFE_Z_MM = 5.0


@dataclass(frozen=True)
class PcbWorkflow:
    copper_gerber: Path
    drill_file: Path
    cutout_file: Path | None = None

    def operation_sequence(self) -> list[str]:
        sequence = ["isolation", "tool_change_probe_z", "drilling"]
        if self.cutout_file:
            sequence.extend(["tool_change_probe_z", "cutout"])
        return sequence


@dataclass
class PcbStage:
    name: str
    gcode_lines: list[str]
    requires_tool_change: bool
    requires_probe_z: bool
    description: str


# --------------------------------------------------------------------------- #
# G-code helpers
# --------------------------------------------------------------------------- #
def _fmt(value: float) -> str:
    """Format a coordinate compactly (3 decimals, no trailing zeros)."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _preamble(lines: list[str]) -> None:
    lines.append("G21")  # mm
    lines.append("G90")  # absolute


def _retract(lines: list[str], safe_z: float) -> None:
    lines.append(f"G0 Z{_fmt(safe_z)}")


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #
def _isolation_paths(copper: GerberData) -> list[list[tuple[float, float]]]:
    """Collect simple polylines to engrave from copper geometry.

    TODO: this engraves the geometry itself, not a true tool-radius offset of
    the copper regions. Adequate as a first functional cut for thin traces.
    """
    paths: list[list[tuple[float, float]]] = []
    for seg in copper.segments:
        paths.append([seg.start, seg.end])
    for region in copper.regions:
        if len(region) >= 2:
            ring = list(region)
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            paths.append(ring)
    for pad in copper.pads:
        # Engrave a small ring around each pad so it stays isolated.
        cx, cy = pad.position
        if pad.shape == "R" and len(pad.size_mm) >= 2:
            hw = pad.size_mm[0] / 2.0
            hh = pad.size_mm[1] / 2.0
        else:
            r = (pad.size_mm[0] / 2.0) if pad.size_mm else ISOLATION_TOOL_DIAMETER_MM
            hw = hh = r
        paths.append(
            [
                (cx - hw, cy - hh),
                (cx + hw, cy - hh),
                (cx + hw, cy + hh),
                (cx - hw, cy + hh),
                (cx - hw, cy - hh),
            ]
        )
    return paths


def _build_isolation_stage(
    copper: GerberData,
    safe_z: float,
    depth: float,
    feed: float,
    plunge: float,
) -> PcbStage:
    lines: list[str] = []
    _preamble(lines)
    _retract(lines, safe_z)

    paths = _isolation_paths(copper)
    for path in paths:
        if len(path) < 2:
            continue
        sx, sy = path[0]
        lines.append(f"G0 Z{_fmt(safe_z)}")
        lines.append(f"G0 X{_fmt(sx)} Y{_fmt(sy)}")
        lines.append(f"G1 Z{_fmt(depth)} F{_fmt(plunge)}")
        for px, py in path[1:]:
            lines.append(f"G1 X{_fmt(px)} Y{_fmt(py)} F{_fmt(feed)}")
    _retract(lines, safe_z)

    return PcbStage(
        name="isolation",
        gcode_lines=lines,
        requires_tool_change=False,
        requires_probe_z=False,
        description=f"Isolation routing: {len(paths)} path(s) at {depth} mm.",
    )


# --------------------------------------------------------------------------- #
# Drilling
# --------------------------------------------------------------------------- #
def _peck_drill(lines: list[str], x: float, y: float, depth: float, safe_z: float) -> None:
    lines.append(f"G0 X{_fmt(x)} Y{_fmt(y)}")
    z = 0.0
    while z > depth:
        z = max(depth, z - DRILL_PECK_MM)
        lines.append(f"G1 Z{_fmt(z)} F{_fmt(DRILL_FEED_MM_MIN)}")
        lines.append(f"G0 Z{_fmt(safe_z)}")


def _build_drill_stages(drill, safe_z: float, depth: float) -> list[PcbStage]:
    """One stage per distinct tool diameter; tool change between groups."""
    # Group hits by diameter (rounded to avoid float noise).
    groups: dict[float, list] = {}
    for hit in drill.hits:
        key = round(hit.diameter_mm, 3)
        groups.setdefault(key, []).append(hit)

    stages: list[PcbStage] = []
    for index, dia in enumerate(sorted(groups)):
        hits = groups[dia]
        lines: list[str] = []
        _preamble(lines)
        _retract(lines, safe_z)
        for hit in hits:
            _peck_drill(lines, hit.position[0], hit.position[1], depth, safe_z)
        _retract(lines, safe_z)

        # First drill group needs a tool change from the isolation engraver;
        # every subsequent group needs a change to a new diameter.
        needs_change = True
        stages.append(
            PcbStage(
                name=f"drill_{_fmt(dia)}mm",
                gcode_lines=lines,
                requires_tool_change=needs_change,
                requires_probe_z=needs_change,
                description=f"Drill {len(hits)} hole(s) with {dia} mm bit.",
            )
        )
    return stages


# --------------------------------------------------------------------------- #
# Cutout
# --------------------------------------------------------------------------- #
def _rect_outline(bounds: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    min_x, min_y, max_x, max_y = bounds
    return [
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
        (min_x, min_y),
    ]


def _outline_from_cutout(cutout: GerberData) -> list[tuple[float, float]]:
    """Pick the longest continuous outline from the cutout layer.

    TODO: stitch disjoint segments into a single ordered loop. For now we use
    the regions if present, otherwise the bounding rectangle of segments.
    """
    if cutout.regions:
        longest = max(cutout.regions, key=len)
        ring = list(longest)
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        return ring
    bounds = cutout.bounds_mm
    if bounds:
        return _rect_outline(bounds)
    return []


def _tab_spans(outline: list[tuple[float, float]]) -> list[int]:
    """Vertices near which we leave a tab (indices into outline segments)."""
    n = max(0, len(outline) - 1)
    if n == 0:
        return []
    count = min(CUTOUT_TAB_COUNT, n)
    step = max(1, n // count)
    return list(range(0, n, step))[:count]


def _build_cutout_stage(
    outline: list[tuple[float, float]],
    safe_z: float,
    depth: float,
    feed: float,
    plunge: float,
) -> PcbStage:
    lines: list[str] = []
    _preamble(lines)
    _retract(lines, safe_z)

    if len(outline) >= 2:
        sx, sy = outline[0]
        lines.append(f"G0 X{_fmt(sx)} Y{_fmt(sy)}")

        passes = max(1, int(round(abs(depth) / CUTOUT_PASS_DEPTH_MM)))
        tab_segments = set(_tab_spans(outline))
        for p in range(1, passes + 1):
            z = max(depth, -(CUTOUT_PASS_DEPTH_MM * p))
            lines.append(f"G1 Z{_fmt(z)} F{_fmt(plunge)}")
            for i in range(1, len(outline)):
                px, py = outline[i]
                # On the final (deepest) pass, lift over tab segments.
                if p == passes and (i - 1) in tab_segments:
                    tab_z = min(z + CUTOUT_TAB_HEIGHT_MM, safe_z)
                    lines.append(f"G1 Z{_fmt(tab_z)} F{_fmt(plunge)}")
                    lines.append(f"G1 X{_fmt(px)} Y{_fmt(py)} F{_fmt(feed)}")
                    lines.append(f"G1 Z{_fmt(z)} F{_fmt(plunge)}")
                else:
                    lines.append(f"G1 X{_fmt(px)} Y{_fmt(py)} F{_fmt(feed)}")
    _retract(lines, safe_z)

    return PcbStage(
        name="cutout",
        gcode_lines=lines,
        requires_tool_change=True,
        requires_probe_z=True,
        description=f"Tabbed cutout: {len(outline) - 1 if outline else 0} segment(s), "
        f"{CUTOUT_TAB_COUNT} tab(s).",
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def generate_pcb_jobs(
    copper_path,
    drill_path,
    cutout_path,
    profile: MachineProfile | None,
    *,
    isolation_depth_mm: float = ISOLATION_DEPTH_MM,
    drill_depth_mm: float = DRILL_DEPTH_MM,
    cutout_depth_mm: float = CUTOUT_DEPTH_MM,
) -> list[PcbStage]:
    """Generate ordered PCB G-code stages.

    Args:
        copper_path: path to the top/bottom copper Gerber (isolation source).
        drill_path: path to the Excellon drill file.
        cutout_path: optional path to a board-outline Gerber; if falsy the
            copper bounding rectangle is used for the cutout.
        profile: machine profile (uses ``safe_z_mm`` for retract height).

    Returns:
        Stages in order: isolation, drill group(s), cutout.
    """
    safe_z = profile.safe_z_mm if profile and profile.safe_z_mm else DEFAULT_SAFE_Z_MM

    copper = parse_gerber_file(Path(copper_path))
    drill = parse_excellon_file(Path(drill_path))

    stages: list[PcbStage] = [
        _build_isolation_stage(
            copper,
            safe_z,
            isolation_depth_mm,
            ISOLATION_FEED_MM_MIN,
            ISOLATION_PLUNGE_MM_MIN,
        )
    ]

    stages.extend(_build_drill_stages(drill, safe_z, drill_depth_mm))

    if cutout_path:
        cutout = parse_gerber_file(Path(cutout_path))
        outline = _outline_from_cutout(cutout)
    else:
        bounds = copper.bounds_mm
        outline = _rect_outline(bounds) if bounds else []

    stages.append(
        _build_cutout_stage(
            outline,
            safe_z,
            cutout_depth_mm,
            CUTOUT_FEED_MM_MIN,
            CUTOUT_PLUNGE_MM_MIN,
        )
    )

    return stages
