"""Geometry operations: project, trim to exact endpoints, and simplify.

The one rule that governs this module: any measurement in meters (trimming
distances, simplification tolerance, later the pen offsets) must be done on a
*projected* line, never on raw lat/lon. Degrees are not a uniform unit of
distance, so buffering/measuring in EPSG:4326 distorts the result. We project
to the local UTM zone (meters) with geopandas, do the math, and project back to
WGS84 for canonical storage.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point
from shapely.ops import substring

from .models import ExtractedRoad, LatLon

_WGS84 = "EPSG:4326"


def project_line_to_utm(line_wgs84: LineString) -> tuple[LineString, int]:
    """Project a WGS84 line to its local UTM CRS. Returns (line_utm, epsg)."""
    series = gpd.GeoSeries([line_wgs84], crs=_WGS84)
    utm_crs = series.estimate_utm_crs()
    projected = series.to_crs(utm_crs).iloc[0]
    return projected, utm_crs.to_epsg()


def project_point_to_utm(point: LatLon, utm_epsg: int) -> Point:
    series = gpd.GeoSeries([Point(point.lon, point.lat)], crs=_WGS84)
    return series.to_crs(epsg=utm_epsg).iloc[0]


def line_utm_to_wgs84(line_utm: LineString, utm_epsg: int) -> LineString:
    series = gpd.GeoSeries([line_utm], crs=utm_epsg)
    return series.to_crs(_WGS84).iloc[0]


def project_line_to_epsg(line_wgs84: LineString, epsg: int) -> LineString:
    """Project a WGS84 line to a specific (known) EPSG.

    Used on load: the stored UTM zone is known, so we reproject to exactly that
    zone rather than re-estimating, keeping the loaded geometry consistent with
    what was saved.
    """
    series = gpd.GeoSeries([line_wgs84], crs=_WGS84)
    return series.to_crs(epsg=epsg).iloc[0]


def trim_to_endpoints(line_utm: LineString, start: Point, finish: Point) -> LineString:
    """Cut a projected line down to the span between two points.

    This is what makes the start and finish *exact*: the routed line runs
    node-to-node, but the user clicked somewhere along an edge. We project each
    click onto the line (nearest point, as a distance along it) and keep only the
    substring between them, rather than snapping out to the nearest intersection.
    """
    d_start = line_utm.project(start)
    d_finish = line_utm.project(finish)
    low, high = sorted((d_start, d_finish))
    return substring(line_utm, low, high)


def simplify(line_utm: LineString, tolerance_m: float) -> LineString:
    """Douglas-Peucker simplification with a tolerance in meters.

    Kept light at the extraction stage to preserve road fidelity; the plotting
    stage simplifies again in paper-mm once the final scale is known.
    """
    if tolerance_m <= 0:
        return line_utm
    return line_utm.simplify(tolerance_m, preserve_topology=False)


def extract_centerline(
    line_wgs84: LineString,
    start: LatLon,
    finish: LatLon,
    simplify_tolerance_m: float = 1.0,
) -> ExtractedRoad:
    """Full geometry pipeline: project -> trim to clicks -> simplify.

    Takes the stitched route (WGS84) plus the two clicked endpoints and returns
    an ``ExtractedRoad`` carrying both coordinate systems and the true length.
    """
    line_utm, utm_epsg = project_line_to_utm(line_wgs84)
    start_utm = project_point_to_utm(start, utm_epsg)
    finish_utm = project_point_to_utm(finish, utm_epsg)

    trimmed_utm = trim_to_endpoints(line_utm, start_utm, finish_utm)
    trimmed_utm = simplify(trimmed_utm, simplify_tolerance_m)

    trimmed_wgs84 = line_utm_to_wgs84(trimmed_utm, utm_epsg)

    return ExtractedRoad(
        line_wgs84=trimmed_wgs84,
        line_utm=trimmed_utm,
        utm_epsg=utm_epsg,
        length_m=trimmed_utm.length,
    )
