"""Compose a text label for a plotted road and render it as single-stroke lines.

The Roads tab can annotate a drawing with its metadata using the same
single-stroke Hershey fonts as the Text tab. The nickname is a title pinned to
the **top-center of the canvas**, 2 mm larger than the rest; the remaining fields
form a block anchored at the user's chosen position (a corner or center):

    ......... <nickname> .........        (canvas top-center, the title)

    <real name>
    <road length>                         <- this block is anchored + nudgeable
    <start coords>  ->  <finish coords>      (both endpoints on one row)
    <date skated>

Any field can be toggled off. The label is produced as shapely LineStrings in
the *same paper-millimeter, y-up space* as the laid-out road (see layout.py), so
it flows through ``svg.render`` and the tab's preview exactly like the road
strokes, and the robot plots it in one pass.

Rendering is split so the interactive preview stays cheap:

    build_rows(...)   -> the per-line spec (text, size, alignment); pure + cheap
    render_rows(...)  -> single-stroke geometry per row (the vpype part; the tab
                         caches this by the row spec + font)
    place_rows(...)   -> stack the rows, anchor the block on the canvas, flip to
                         y-up (cheap; re-run on every position/nudge/spacing edit)

``vpype`` is imported lazily so importing this module (and the Roads tab) stays
light for callers that never draw a label.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString

from .models import ExtractedRoad, LabelConfig, RoadMetadata

# vpype stores geometry in CSS pixels (96 px == 1 inch == 25.4 mm).
_PX_PER_MM = 96 / 25.4

# The nickname title is drawn this much larger than the body text.
NICKNAME_SIZE_BONUS_MM = 2.0

# Anchor presets -> (horizontal, vertical) fraction of the usable area, in the
# y-*down* canvas frame: (0, 0) is top-left, (1, 1) is bottom-right.
_ANCHORS = {
    "Top Left": (0.0, 0.0),
    "Top Right": (1.0, 0.0),
    "Bottom Left": (0.0, 1.0),
    "Bottom Right": (1.0, 1.0),
    "Center": (0.5, 0.5),
}
POSITIONS = list(_ANCHORS)


@dataclass(frozen=True)
class RowSpec:
    """One line of the label before rendering: its text, size, and role.

    ``is_title`` rows (the nickname) are pinned to the canvas top-center; the rest
    are body rows stacked in an anchored block and aligned within it to match the
    block's horizontal position (left edge / center / right edge — see
    ``place_rows``).
    """

    text: str
    size_mm: float
    is_title: bool = False


@dataclass
class RenderedRow:
    """A rendered line: single-stroke geometry normalized to origin (y-down mm)."""

    polylines: list[list[tuple[float, float]]]  # each point in [0, width]x[0, height]
    size_mm: float
    width: float
    height: float
    is_title: bool


def build_rows(
    metadata: RoadMetadata, road: ExtractedRoad | None, config: LabelConfig
) -> list[RowSpec]:
    """Assemble the label's rows, in display order, from the selected fields.

    The nickname is the title (``size_mm`` + a fixed bonus), pinned to the canvas
    top-center; everything else is body text at ``size_mm``. Start/finish
    coordinates share a single row.
    """
    base = config.size_mm
    rows: list[RowSpec] = []

    if config.show_nickname and metadata.nickname:
        rows.append(RowSpec(metadata.nickname.strip(),
                            base + NICKNAME_SIZE_BONUS_MM, is_title=True))
    if config.show_name and metadata.real_name:
        rows.append(RowSpec(metadata.real_name.strip(), base))
    if config.show_distance and road is not None:
        km = road.length_m / 1000
        rows.append(RowSpec(f"{km:.1f} km / {km * 0.621:.1f} mi", base))
    if config.show_coords and metadata.start and metadata.finish:
        s, f = metadata.start, metadata.finish
        rows.append(RowSpec(
            f"{s.lat:.4f}, {s.lon:.4f}  ->  {f.lat:.4f}, {f.lon:.4f}", base))
    if config.show_date and metadata.date_first_skated:
        rows.append(RowSpec(metadata.date_first_skated.strip(), base))

    return [r for r in rows if r.text]


def _render_line(text: str, font: str, size_mm: float):
    """Render a single line to normalized polylines + (width, height) in mm.

    Returns (polylines, width, height) with the block's min corner at (0, 0),
    or None if the text produced no geometry.
    """
    from vpype_cli import execute  # lazy: pulls in vpype

    safe = text.replace('"', "'")  # keep the double-quoted CLI arg intact
    doc = execute(f'text -f "{font}" -s {size_mm}mm -p 0mm 0mm "{safe}"')

    polylines: list[list[tuple[float, float]]] = []
    for lc in doc.layers.values():
        for arr in lc:
            pts = [(p.real / _PX_PER_MM, p.imag / _PX_PER_MM) for p in arr]
            if len(pts) >= 2:
                polylines.append(pts)
    if not polylines:
        return None

    xs = [x for pl in polylines for x, _ in pl]
    ys = [y for pl in polylines for _, y in pl]
    min_x, min_y = min(xs), min(ys)
    norm = [[(x - min_x, y - min_y) for x, y in pl] for pl in polylines]
    return norm, max(xs) - min_x, max(ys) - min_y


def render_rows(specs: list[RowSpec], font: str) -> list[RenderedRow] | None:
    """Render each row's single-stroke geometry. None if nothing to draw."""
    rendered: list[RenderedRow] = []
    for spec in specs:
        if not spec.text.strip() or spec.size_mm <= 0:
            continue
        result = _render_line(spec.text, font, spec.size_mm)
        if result is None:
            continue
        polylines, width, height = result
        rendered.append(RenderedRow(polylines, spec.size_mm, width, height,
                                    spec.is_title))
    return rendered or None


def _emit_row(row: RenderedRow, tx: float, ty: float,
              canvas_h_mm: float) -> list[LineString]:
    """Place one normalized row at (tx, ty) in y-down mm and flip to y-up strokes."""
    return [
        LineString([(tx + x, canvas_h_mm - (ty + y)) for x, y in pl])
        for pl in row.polylines
    ]


def _body_layout(
    body: list[RenderedRow], config: LabelConfig,
    canvas_w_mm: float, canvas_h_mm: float, inset_mm: float,
) -> tuple[list[float], float, float, float, float, float]:
    """Geometry of the anchored body block, in y-down mm.

    Returns (row_tops, tx0, ty0, block_w, block_h, hx): the per-row top offsets
    within the block, the block's top-left origin, its size, and the horizontal
    anchor fraction ``hx`` (0 left / 0.5 center / 1 right). Shared by
    ``place_rows`` (to draw the rows) and ``obstacle_boxes`` (to report the block
    footprint) so the two never drift.
    """
    block_w = max(r.width for r in body)
    tops: list[float] = []
    y = 0.0
    for r in body:
        tops.append(y)
        y += r.size_mm * config.line_spacing
    block_h = tops[-1] + body[-1].height

    hx, hy = _ANCHORS.get(config.position, (0.0, 1.0))
    avail_w = max(canvas_w_mm - 2 * inset_mm, 0.0)
    avail_h = max(canvas_h_mm - 2 * inset_mm, 0.0)
    tx0 = inset_mm + hx * (avail_w - block_w) + config.offset_x_mm
    ty0 = inset_mm + hy * (avail_h - block_h) - config.offset_y_mm
    return tops, tx0, ty0, block_w, block_h, hx


def place_rows(
    rendered: list[RenderedRow] | None,
    config: LabelConfig,
    canvas_w_mm: float,
    canvas_h_mm: float,
    inset_mm: float,
) -> list[LineString]:
    """Place the label and flip it to y-up mm strokes.

    The title (nickname) is centered across the full canvas width and pinned to
    the top edge (inset by ``inset_mm``). The body rows stack top-to-top by
    ``size_mm * line_spacing`` into a block anchored inside the canvas minus
    ``inset_mm`` at ``config.position`` and nudged by the config offsets
    (+x right, +y up); each body row is aligned within the block to match the
    block's horizontal position (left edge for a left anchor, centered for a
    center anchor, right edge for a right anchor).
    """
    if not rendered:
        return []

    strokes: list[LineString] = []

    # Title: centered on the canvas, at the top edge.
    for r in (r for r in rendered if r.is_title):
        strokes += _emit_row(r, (canvas_w_mm - r.width) / 2, inset_mm, canvas_h_mm)

    # Body block: stacked and anchored at the chosen position.
    body = [r for r in rendered if not r.is_title]
    if body:
        tops, tx0, ty0, block_w, _, hx = _body_layout(
            body, config, canvas_w_mm, canvas_h_mm, inset_mm)
        for r, top in zip(body, tops):
            x_off = hx * (block_w - r.width)
            strokes += _emit_row(r, tx0 + x_off, ty0 + top, canvas_h_mm)

    return strokes


def obstacle_boxes(
    rendered: list[RenderedRow] | None,
    config: LabelConfig,
    canvas_w_mm: float,
    canvas_h_mm: float,
    inset_mm: float,
) -> list[tuple[float, float, float, float]]:
    """Rectangles the placed label occupies, (minx, miny, maxx, maxy) in y-up mm.

    One box for the top-center title and one for the anchored body block, matching
    exactly what ``place_rows`` draws. The Roads tab feeds these to ``layout`` so
    the road is fit into the space the label leaves free.
    """
    if not rendered:
        return []

    boxes: list[tuple[float, float, float, float]] = []

    # Title: centered on the canvas, at the top edge (y-down [inset, inset+h]).
    for r in (r for r in rendered if r.is_title):
        x0 = (canvas_w_mm - r.width) / 2
        boxes.append((x0, canvas_h_mm - inset_mm - r.height,
                      x0 + r.width, canvas_h_mm - inset_mm))

    # Body block: the anchored, stacked rows (y-down [ty0, ty0+block_h]).
    body = [r for r in rendered if not r.is_title]
    if body:
        _, tx0, ty0, block_w, block_h, _ = _body_layout(
            body, config, canvas_w_mm, canvas_h_mm, inset_mm)
        boxes.append((tx0, canvas_h_mm - (ty0 + block_h),
                      tx0 + block_w, canvas_h_mm - ty0))

    return boxes


def render_label(
    metadata: RoadMetadata,
    road: ExtractedRoad | None,
    config: LabelConfig,
    canvas_w_mm: float,
    canvas_h_mm: float,
    inset_mm: float,
) -> list[LineString]:
    """One-shot convenience: metadata + config -> placed label strokes (y-up mm).

    The Roads tab uses the three-step form for caching; this is for spikes/tests.
    """
    if not config.enabled:
        return []
    rows = build_rows(metadata, road, config)
    rendered = render_rows(rows, config.font)
    return place_rows(rendered, config, canvas_w_mm, canvas_h_mm, inset_mm)
