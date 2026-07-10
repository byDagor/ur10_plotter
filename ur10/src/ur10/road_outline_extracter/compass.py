"""A minimal north compass drawn in the bottom-right corner of the canvas.

When the road is rotated to fit the page (``PlotConfig.rotation_deg``), north is
no longer "up". This draws a small compass — a symmetric rhombus needle (two
equal back-to-back isosceles triangles) with an upright "N" marking the north
end — whose needle points wherever true north ended up, so the viewer can orient
the drawing regardless of how it was spun.

Everything is emitted as shapely LineStrings in the **same y-up paper-millimeter
space as the road** (see layout.py), so the compass merges straight into the
stroke list and flows through ``svg.render``, the tab preview, and the robot
identically. It is pure geometry (the "N" is three strokes) — no font needed.

North direction: ``layout`` rotates the road counter-clockwise by
``rotation_deg`` (shapely convention), so north — originally +y — rotates with
it to ``(-sin θ, cos θ)`` in the y-up frame. The needle/arrowhead rotate with
north; the "N" stays upright so it is always readable.
"""

from __future__ import annotations

import math

from shapely.geometry import LineString


def render(
    rotation_deg: float,
    canvas_w_mm: float,
    canvas_h_mm: float,
    inset_mm: float,
    radius_mm: float = 9.0,
) -> list[LineString]:
    """Compass strokes (y-up mm) in the bottom-right corner. [] if size <= 0.

    ``radius_mm`` is the overall footprint radius from the center to the "N".
    """
    r = radius_mm
    if r <= 0:
        return []

    # Center: inset from the bottom-right corner by the margin + the footprint.
    cx = canvas_w_mm - inset_mm - r
    cy = inset_mm + r  # y-up: bottom is small y

    th = math.radians(rotation_deg)
    nx, ny = -math.sin(th), math.cos(th)   # north, after the road's CCW rotation
    px, py = math.cos(th), math.sin(th)     # perpendicular (needle half-width)

    strokes: list[LineString] = []

    # Needle: a symmetric slender rhombus (two equal back-to-back isosceles
    # triangles). The E/W tips meet at the center; their shared base is drawn as
    # a divider so the two triangles read distinctly.
    n_tip = (cx + nx * 0.6 * r, cy + ny * 0.6 * r)
    s_tip = (cx - nx * 0.6 * r, cy - ny * 0.6 * r)
    e_mid = (cx + px * 0.14 * r, cy + py * 0.14 * r)
    w_mid = (cx - px * 0.14 * r, cy - py * 0.14 * r)
    strokes.append(LineString([n_tip, e_mid, s_tip, w_mid, n_tip]))  # rhombus
    strokes.append(LineString([w_mid, e_mid]))                       # shared base

    # Upright "N" beyond the north tip, drawn as three strokes.
    nw, nh = 0.22 * r, 0.34 * r
    x0 = cx + nx * 0.82 * r - nw / 2
    y0 = cy + ny * 0.82 * r - nh / 2
    strokes.append(LineString([(x0, y0), (x0, y0 + nh)]))            # left stem
    strokes.append(LineString([(x0, y0 + nh), (x0 + nw, y0)]))       # diagonal
    strokes.append(LineString([(x0 + nw, y0), (x0 + nw, y0 + nh)]))  # right stem

    return strokes
