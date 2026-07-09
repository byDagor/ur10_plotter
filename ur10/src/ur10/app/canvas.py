"""PreviewCanvas: a resizable DPG drawlist that renders vector geometry.

Geometry is cached in *data space* (SVG/robot coordinates) as a list of items,
so the canvas can re-fit to the drawlist at any size (window resize) without the
source data. Items are also appended incrementally for animated drawing (the
UR10 demo / live plot), drawn one-per-frame via pump().
"""

import threading
from xml.dom import minidom

import dearpygui.dearpygui as dpg

from robot.svg_parser import _get_points_from_element
from .theme import CANVAS_BG, PAPER_EDGE, INK, CMYK

ALL_CANVASES = []
DOT_RATIO = 0.85


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def bounds_of(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def make_tf(bounds, width, height, pad=28, flip_y=False):
    min_x, min_y, max_x, max_y = bounds
    span_x = (max_x - min_x) or 1.0
    span_y = (max_y - min_y) or 1.0
    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)
    off_x = (width - span_x * scale) / 2
    off_y = (height - span_y * scale) / 2

    def tf(x, y):
        sx = off_x + (x - min_x) * scale
        sy = height - (off_y + (y - min_y) * scale) if flip_y else off_y + (y - min_y) * scale
        return [sx, sy]
    return tf


def polyline_is_dot(pl, eps=1e-6):
    if len(pl) == 1:
        return True
    xs = [p[0] for p in pl]
    ys = [p[1] for p in pl]
    return (max(xs) - min(xs) < eps) and (max(ys) - min(ys) < eps)


def detect_dots(items, is_dot_fn):
    if not items:
        return False
    return sum(1 for it in items if is_dot_fn(it)) / len(items) > DOT_RATIO


def load_svg_polylines(path):
    doc = minidom.parse(path)
    polylines = []
    for tag in ("path", "polyline", "polygon", "line"):
        for el in doc.getElementsByTagName(tag):
            polylines.extend(_get_points_from_element(el))
    doc.unlink()
    return polylines


def svg_to_items(path):
    """Parse an SVG file into (items, bounds, is_dots) for a static preview."""
    polylines = load_svg_polylines(path)
    all_pts = [p for pl in polylines for p in pl]
    if not all_pts:
        return [], None, False
    is_dots = detect_dots(polylines, polyline_is_dot)
    items = []
    for pl in polylines:
        if is_dots or polyline_is_dot(pl):
            items.append(("dot", pl[0][0], pl[0][1], INK))
        else:
            items.append(("poly", pl, INK))
    return items, bounds_of(all_pts), is_dots


def document_to_items(document, is_cmyk=False, fill=False):
    """Convert a vpype.Document into preview items + bounds.

    fill=True renders closed polygons filled (dither dots are circle polygons);
    line art (Flow/Hatched) uses fill=False so shapes render as strokes.
    """
    items = []
    for layer_id, lc in document.layers.items():
        color = CMYK.get(layer_id, INK) if is_cmyk else INK
        for line in lc:
            pts = [(p.real, p.imag) for p in line]
            if polyline_is_dot(pts):          # single point or zero-length (dither dot)
                items.append(("dot", pts[0][0], pts[0][1], color))
            elif fill and len(pts) > 2:       # closed polygon -> filled dot
                items.append(("fill", pts, color))
            elif len(pts) > 1:
                items.append(("poly", pts, color))
    b = document.bounds() if not document.is_empty() else None
    return items, b


# --------------------------------------------------------------------------- #
# Canvas widget
# --------------------------------------------------------------------------- #
class PreviewCanvas:
    def __init__(self, tag, flip_y=False):
        self.tag = tag
        self.flip_y = flip_y
        self.items = []
        self.bounds = None
        self.tf = None
        self.w = 700
        self.h = 560
        self._lock = threading.Lock()
        self._drawn = 0
        ALL_CANVASES.append(self)

    # -- construction: call inside a container to create the drawlist -- #
    def build(self):
        with dpg.drawlist(width=self.w, height=self.h, tag=self.tag):
            pass

    # -- content -- #
    def set_items(self, items, bounds):
        with self._lock:
            self.items = list(items)
            self.bounds = bounds
            self._drawn = 0
        self.redraw()

    def append_item(self, item):
        with self._lock:
            self.items.append(item)

    def set_bounds(self, bounds):
        with self._lock:
            self.items = []
            self.bounds = bounds
            self._drawn = 0
        self.redraw()

    def clear(self):
        with self._lock:
            self.items = []
            self.bounds = None
            self._drawn = 0
        self.redraw()

    # -- sizing -- #
    def resize(self, w, h):
        self.w = max(int(w), 120)
        self.h = max(int(h), 120)
        if dpg.does_item_exist(self.tag):
            dpg.configure_item(self.tag, width=self.w, height=self.h)
        self.redraw()

    # -- rendering -- #
    def _paper(self):
        dpg.draw_rectangle([0, 0], [self.w, self.h], fill=CANVAS_BG, color=CANVAS_BG,
                           parent=self.tag)
        dpg.draw_rectangle([16, 16], [self.w - 16, self.h - 16], color=PAPER_EDGE,
                           thickness=1.0, parent=self.tag)

    def _blit(self, item):
        tf = self.tf
        if item[0] == "poly":
            dpg.draw_polyline([tf(x, y) for x, y in item[1]], color=item[2],
                              thickness=1.0, parent=self.tag)
        elif item[0] == "dot":
            dpg.draw_circle(tf(item[1], item[2]), 1.5, fill=item[3], color=item[3],
                            parent=self.tag)
        elif item[0] == "fill":
            dpg.draw_polygon([tf(x, y) for x, y in item[1]], fill=item[2], color=item[2],
                             thickness=1.0, parent=self.tag)
        elif item[0] == "line":
            dpg.draw_line(tf(item[1], item[2]), tf(item[3], item[4]), color=item[5],
                          thickness=1.4, parent=self.tag)

    def redraw(self):
        if not dpg.does_item_exist(self.tag):
            return
        dpg.delete_item(self.tag, children_only=True)
        self._paper()
        if self.bounds is None:
            self._drawn = 0
            return
        self.tf = make_tf(self.bounds, self.w, self.h, flip_y=self.flip_y)
        with self._lock:
            items = list(self.items)
        for it in items:
            self._blit(it)
        self._drawn = len(items)

    def pump(self):
        """Draw items appended since the last frame (animation)."""
        if self.tf is None or not dpg.does_item_exist(self.tag):
            return
        with self._lock:
            n = len(self.items)
            new = self.items[self._drawn:n]
        for it in new:
            self._blit(it)
        self._drawn = n


def pump_all():
    for c in ALL_CANVASES:
        c.pump()
