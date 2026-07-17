"""The plotting stage: place a road on the canvas and bold it into strokes.

Input is the road's centerline in UTM meters (true scale). Output is a set of
LineStrings in paper millimeters, ready for SVG. The transform order is
deliberate and matches what the UI promises the user:

    rotate (around centroid)
      -> fit: scale so the *rotated* bounding box fills the largest label-free
              rectangle inside the canvas margin (the whole area if no label)
        -> place: center in that rectangle, then apply the user's x/y nudge
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


Rect = tuple[float, float, float, float]  # (minx, miny, maxx, maxy)


def _rects_overlap(a: Rect, b: Rect, eps: float = 1e-6) -> bool:
    """True if rectangles ``a`` and ``b`` share interior area (touching edges
    don't count)."""
    return (a[0] < b[2] - eps and b[0] < a[2] - eps and
            a[1] < b[3] - eps and b[1] < a[3] - eps)


def _largest_free_fit(avail: Rect, obstacles: list[Rect],
                      box_w: float, box_h: float) -> Rect:
    """Sub-rectangle of ``avail`` avoiding every obstacle that best fits a
    ``box_w`` x ``box_h`` drawing.

    Returns the rectangle maximizing the uniform fit scale
    ``min(w / box_w, h / box_h)``. A maximal empty rectangle always has each edge
    on the container or an obstacle edge, so scanning every rectangle spanned by
    those candidate cut-lines is exact -- and cheap here (a handful of obstacles,
    so a few candidate lines each way). Falls back to ``avail`` if nothing is free
    (e.g. the label covers the page).
    """
    ax0, ay0, ax1, ay1 = avail
    xs = {ax0, ax1}
    ys = {ay0, ay1}
    for ox0, oy0, ox1, oy1 in obstacles:
        xs.update(x for x in (ox0, ox1) if ax0 < x < ax1)
        ys.update(y for y in (oy0, oy1) if ay0 < y < ay1)
    xs = sorted(xs)
    ys = sorted(ys)

    best = avail
    best_scale = -1.0
    for i in range(len(xs) - 1):
        for j in range(i + 1, len(xs)):
            w = xs[j] - xs[i]
            for k in range(len(ys) - 1):
                for m in range(k + 1, len(ys)):
                    rect = (xs[i], ys[k], xs[j], ys[m])
                    if any(_rects_overlap(rect, o) for o in obstacles):
                        continue
                    scale = min(w / box_w, (ys[m] - ys[k]) / box_h)
                    if scale > best_scale:
                        best_scale = scale
                        best = rect
    return best


def place_centerline(
    line_utm: LineString,
    config: PlotConfig,
    obstacles: list[Rect] = (),
    clearance_mm: float = 4.0,
) -> tuple[LineString, float, float, float]:
    """Rotate, fit-to-canvas, and center+nudge the centerline into paper mm.

    ``obstacles`` are (minx, miny, maxx, maxy) rectangles in paper mm (y-up, the
    same frame as the returned line) that the road must not overlap -- typically
    the label's title and body block. The road is fit into the largest
    obstacle-free rectangle inside the canvas margin (keeping a ``clearance_mm``
    gap) rather than the whole canvas; with no obstacles this is the plain
    fit-to-canvas, unchanged.

    Returns (placed_line_mm, scale_mm_per_m, draw_w_mm, draw_h_mm).
    """
    rotated = affinity.rotate(line_utm, config.rotation_deg, origin="centroid")

    minx, miny, maxx, maxy = rotated.bounds
    box_w = maxx - minx
    box_h = maxy - miny

    margin = config.margin_mm
    avail = (margin, margin,
             config.canvas_w_mm - margin, config.canvas_h_mm - margin)
    if avail[2] <= avail[0] or avail[3] <= avail[1]:
        raise ValueError("margin_mm is too large for the canvas")

    # Fit into the largest label-free rectangle (the whole available area when
    # there are no obstacles), keeping a clearance gap around the label.
    fit = avail
    if obstacles:
        inflated = [(x0 - clearance_mm, y0 - clearance_mm,
                     x1 + clearance_mm, y1 + clearance_mm)
                    for x0, y0, x1, y1 in obstacles]
        fit = _largest_free_fit(avail, inflated, box_w, box_h)
    fx0, fy0, fx1, fy1 = fit
    fit_w = fx1 - fx0
    fit_h = fy1 - fy0

    # Uniform scale (preserve aspect ratio) so the rotated bbox fits inside the
    # fit rectangle. This is the "fit to canvas" the user chose.
    scale = min(fit_w / box_w, fit_h / box_h)

    # Anchor bbox min at origin, scale, then center in the fit rect + user nudge.
    moved = affinity.translate(rotated, -minx, -miny)
    scaled = affinity.scale(moved, xfact=scale, yfact=scale, origin=(0, 0))

    draw_w = box_w * scale
    draw_h = box_h * scale
    off_x = fx0 + (fit_w - draw_w) / 2 + config.pos_x_mm
    off_y = fy0 + (fit_h - draw_h) / 2 + config.pos_y_mm
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


def plan(line_utm: LineString, config: PlotConfig,
         obstacles: list[Rect] = (), clearance_mm: float = 4.0) -> PlotResult:
    """Full plotting stage: place the centerline, then bold it into strokes.

    ``obstacles`` (paper-mm rectangles, e.g. the label's footprint) are kept
    clear of the road by ``clearance_mm`` -- see ``place_centerline``.
    """
    placed, scale, draw_w, draw_h = place_centerline(
        line_utm, config, obstacles, clearance_mm)
    strokes = make_strokes(placed, config)
    return PlotResult(
        strokes=strokes,
        centerline_mm=placed,
        scale_mm_per_m=scale,
        draw_w_mm=draw_w,
        draw_h_mm=draw_h,
    )
