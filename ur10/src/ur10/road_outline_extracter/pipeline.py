"""End-to-end extraction orchestration: clicked points in, ExtractedRoad out.

Thin glue over osm + geometry so the UI (and scripts) have one call for the
whole capture pipeline. The clicked points are ordered start -> ... -> finish;
everything between the ends is treated as a waypoint the route must pass through.
"""

from __future__ import annotations

from . import geometry, osm
from .models import ExtractedRoad, LatLon


def extract_road(
    start: LatLon,
    finish: LatLon,
    waypoints: list[LatLon] | None = None,
    network_type: str = "drive",
    simplify_tolerance_m: float = 1.0,
) -> ExtractedRoad:
    """Download, route, stitch, project, trim, and simplify into a centerline."""
    waypoints = list(waypoints or [])
    graph = osm.download_graph([start, *waypoints, finish], network_type=network_type)
    route = osm.route_nodes(graph, start, finish, waypoints)
    line_wgs84 = osm.route_linestring(graph, route)
    return geometry.extract_centerline(line_wgs84, start, finish, simplify_tolerance_m)
