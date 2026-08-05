"""Core data types for road extraction.

Phase 1 keeps this deliberately small: just the geographic input point and the
result of extracting a road's centerline. Metadata and PlotConfig arrive in
later phases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shapely.geometry import LineString


@dataclass(frozen=True)
class LatLon:
    """A WGS84 geographic point. Note the field order: latitude first."""

    lat: float
    lon: float

    def as_xy(self) -> tuple[float, float]:
        """Return (x, y) = (lon, lat) as used by shapely/GeoJSON."""
        return (self.lon, self.lat)

    @classmethod
    def parse(cls, text: str) -> LatLon | None:
        """Parse 'lat, lon' as copied from Google Maps (comma or space separated).

        Returns None if the text isn't exactly two numbers in valid lat/lon range.
        """
        parts = [p for p in re.split(r"[,\s]+", text.strip()) if p]
        if len(parts) != 2:
            return None
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return cls(lat, lon)


@dataclass
class ExtractedRoad:
    """The centerline of an extracted road, in two coordinate systems.

    ``line_wgs84`` is the canonical geometry (degrees) suitable for GeoJSON and
    for redrawing on a map. ``line_utm`` is the same line projected to a local
    metric CRS (meters), which is what any distance/offset math must use.

    ``elevation_loss_m`` (total descent) and ``max_grade_pct`` (steepest sustained
    downhill) are optional, sampled from a DEM at extract time (see
    elevation.py); they are ``None`` for roads extracted before elevation existed
    or when the elevation service was unavailable.
    """

    line_wgs84: LineString
    line_utm: LineString
    utm_epsg: int
    length_m: float
    elevation_loss_m: float | None = None
    max_grade_pct: float | None = None

    @property
    def n_points(self) -> int:
        return len(self.line_utm.coords)


@dataclass
class PlotConfig:
    """Everything the plotting stage needs to turn a road into a plotter SVG.

    Distances are in millimeters of paper. The road is scaled to *fit* the
    canvas (minus ``margin_mm``) after rotation, then centered and nudged by
    ``pos_x_mm`` / ``pos_y_mm``. The line is drawn as ``stroke_count`` parallel
    passes spaced ``stroke_offset_mm`` apart to bold it up on a large print;
    ``stroke_offset_mm`` slightly under ``pen_width_mm`` makes the passes overlap
    into one solid line.
    """

    canvas_w_mm: float
    canvas_h_mm: float
    margin_mm: float = 10.0
    pen_width_mm: float = 0.7
    stroke_count: int = 1
    stroke_offset_mm: float = 0.65
    rotation_deg: float = 0.0
    pos_x_mm: float = 0.0  # nudge from centered position, +x is right
    pos_y_mm: float = 0.0  # nudge from centered position, +y is up
    simplify_tolerance_mm: float = 0.0


@dataclass
class LabelConfig:
    """Styling for the optional on-canvas annotations of a plotted road.

    The text label composes stored metadata (real name, nickname, date,
    coordinates) plus a distance readout into single-stroke Hershey text (same
    fonts as the Text tab). It is rendered in the same paper-millimeter space as
    the road and written into the same SVG, so the robot draws it in the one
    pass. ``position`` is an anchor preset (see ``label.POSITIONS``);
    ``offset_x_mm`` / ``offset_y_mm`` nudge from that anchor (+x right, +y up),
    matching the plot nudge convention.

    A separate north ``compass`` (see ``compass.py``) can be toggled on; it is
    pinned to the bottom-right corner and its needle tracks the plot rotation.
    """

    enabled: bool = False
    show_name: bool = True
    show_nickname: bool = False
    show_date: bool = True
    show_coords: bool = False
    show_distance: bool = False
    show_elevation_loss: bool = False
    show_max_grade: bool = False
    font: str = "futural"
    size_mm: float = 4.0
    line_spacing: float = 1.4
    position: str = "Bottom Left"
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    clearance_mm: float = 4.0  # gap kept between the road and the label footprint
    compass_enabled: bool = False
    compass_radius_mm: float = 9.0


@dataclass
class RoadMetadata:
    """User-supplied facts about a run. All optional; dates are ISO strings.

    ``start`` / ``finish`` record the exact clicked endpoints (handy for redraw
    and reference); ``created_at`` is stamped by the storage layer on first save.
    """

    nickname: str | None = None
    real_name: str | None = None
    date_first_skated: str | None = None  # "YYYY-MM-DD"
    start: LatLon | None = None
    finish: LatLon | None = None
    created_at: str | None = None  # ISO 8601, stamped on save


@dataclass
class RoadRun:
    """A saved run: identity, geometry, metadata, and last-used plot settings."""

    slug: str
    road: ExtractedRoad
    metadata: RoadMetadata
    plot_config: PlotConfig | None = None
    label_config: LabelConfig | None = None
