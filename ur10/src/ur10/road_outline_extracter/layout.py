"""The plotting stage: place a road on the canvas and bold it into strokes.

Input is the road's centerline in UTM meters (true scale). Output is a set of
LineStrings in paper millimeters, ready for SVG. The transform order is
deliberate and matches what the UI promises the user:

    rotate (around centroid)
      -> fit: scale so the *rotated* bounding box fills the canvas minus margin
        -> place: center on the canvas, then apply the user's x/y nudge
          -> multi-stroke: N parallel offset copies to bold the line

All coordinates here use a y-*up* convention (like a map / matplotlib). svg.py
flips to SVG's y-down at write time. Offsets are computed here, in paper mm,
because the pen offset is a paper measurement, not a geographic one.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely import affinity
from shapely.geometry import LineString, MultiLineString

from .models import PlotConfig


@dataclass
class PlotResult:
    """The laid-out road: bold strokes plus useful diagnostics."""

    strokes: list[LineString]
    centerline_mm: LineString
    scale_mm_per_m: float
    draw_w_mm: float
    draw_h_mm: float


def _offset_positions(count: int, offset_mm: float) -> list[float]:
    """Perpendicular offsets for ``count`` passes, symmetric about the center.

    count=1 -> [0]; count=2 -> [-d/2, +d/2]; count=3 -> [-d, 0, +d]; and so on.
    """
    return [(i - (count - 1) / 2) * offset_mm for i in range(count)]


def _as_lines(geom) -> list[LineString]:
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return [g for g in geom.geoms if not g.is_empty]
    return []


def place_centerline(line_utm: LineString, config: PlotConfig) -> tuple[LineString, float, float, float]:
    """Rotate, fit-to-canvas, and center+nudge the centerline into paper mm.

    Returns (placed_line_mm, scale_mm_per_m, draw_w_mm, draw_h_mm).
    """
    rotated = affinity.rotate(line_utm, config.rotation_deg, origin="centroid")

    minx, miny, maxx, maxy = rotated.bounds
    box_w = maxx - minx
    box_h = maxy - miny

    avail_w = config.canvas_w_mm - 2 * config.margin_mm
    avail_h = config.canvas_h_mm - 2 * config.margin_mm
    if avail_w <= 0 or avail_h <= 0:
        raise ValueError("margin_mm is too large for the canvas")

    # Uniform scale (preserve aspect ratio) so the rotated bbox fits inside the
    # available area. This is the "fit to canvas" the user chose.
    scale = min(avail_w / box_w, avail_h / box_h)

    # Anchor bbox min at origin, scale, then center on the canvas + user nudge.
    moved = affinity.translate(rotated, -minx, -miny)
    scaled = affinity.scale(moved, xfact=scale, yfact=scale, origin=(0, 0))

    draw_w = box_w * scale
    draw_h = box_h * scale
    off_x = (config.canvas_w_mm - draw_w) / 2 + config.pos_x_mm
    off_y = (config.canvas_h_mm - draw_h) / 2 + config.pos_y_mm
    placed = affinity.translate(scaled, off_x, off_y)

    if config.simplify_tolerance_mm > 0:
        placed = placed.simplify(config.simplify_tolerance_mm, preserve_topology=False)

    return placed, scale, draw_w, draw_h


def make_strokes(centerline_mm: LineString, config: PlotConfig) -> list[LineString]:
    """Generate ``stroke_count`` parallel passes around the centerline.

    The zero-offset pass is the centerline itself; the rest use shapely's
    ``offset_curve``. Offset results can split into several pieces on sharp
    curves, so each is flattened to its constituent LineStrings.
    """
    strokes: list[LineString] = []
    for offset in _offset_positions(config.stroke_count, config.stroke_offset_mm):
        if abs(offset) < 1e-9:
            strokes.append(centerline_mm)
        else:
            strokes.extend(_as_lines(centerline_mm.offset_curve(offset)))
    return strokes


def plan(line_utm: LineString, config: PlotConfig) -> PlotResult:
    """Full plotting stage: place the centerline, then bold it into strokes."""
    placed, scale, draw_w, draw_h = place_centerline(line_utm, config)
    strokes = make_strokes(placed, config)
    return PlotResult(
        strokes=strokes,
        centerline_mm=placed,
        scale_mm_per_m=scale,
        draw_w_mm=draw_w,
        draw_h_mm=draw_h,
    )
