"""OpenStreetMap access: download a local road graph and route across it.

This is the "capture" half of extraction. Given a start point, a finish point,
and optional waypoints (all lat/lon), we:

1. download the drivable road network covering the corridor, then
2. route start -> waypoints... -> finish along that network, and
3. stitch the traversed edges into a single WGS84 centerline LineString that
   follows the road's real curves (not straight node-to-node segments).

Everything here works in WGS84 (degrees). Projection to meters happens in
``geometry.py``.
"""

from __future__ import annotations

import math

import numpy as np
import osmnx as ox
import osmnx.routing
from shapely.geometry import LineString

from .models import LatLon


def _bbox_center_and_radius(
    points: list[LatLon], padding_m: float
) -> tuple[tuple[float, float], float]:
    """Center point and half-side (meters) of a square bbox covering ``points``.

    ``ox.graph_from_point(..., dist_type="bbox")`` builds a square of side
    ``2 * dist`` around the center, so we return the distance from the center to
    the farthest corner plus padding. Padding matters: switchbacks bulge outside
    the straight-line corridor between endpoints and would otherwise be clipped.
    """
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    north, south = max(lats), min(lats)
    east, west = max(lons), min(lons)

    center_lat = (north + south) / 2
    center_lon = (east + west) / 2

    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(center_lat))
    half_height_m = (north - south) / 2 * m_per_deg_lat
    half_width_m = (east - west) / 2 * m_per_deg_lon
    radius_m = math.hypot(half_height_m, half_width_m) + padding_m

    return (center_lat, center_lon), radius_m


def download_graph(
    points: list[LatLon],
    network_type: str = "drive",
    padding_m: float = 1000.0,
):
    """Download the OSM road graph covering all ``points`` (plus padding).

    ``network_type="drive"`` restricts to drivable roads, which keeps routing on
    the paved road and avoids shortcuts across footpaths/trails. Pass ``"all"``
    for spots that live on non-drivable ways.
    """
    center, radius_m = _bbox_center_and_radius(points, padding_m)
    # simplify=False for two reasons: (1) osmnx 2.1.0's simplification collapses
    # some sparse rural drive networks (e.g. Mount Hamilton Rd) to a single node,
    # and (2) the unsimplified graph keeps every OSM vertex, so the stitched
    # centerline captures the road's curves at full resolution. We reduce vertex
    # count later with a metric-aware simplify in geometry.py.
    return ox.graph_from_point(
        center,
        dist=radius_m,
        dist_type="bbox",
        network_type=network_type,
        simplify=False,
    )


def _nearest_node(graph, point: LatLon) -> int:
    """Nearest graph node to a lat/lon, by brute force over node coordinates.

    osmnx's own ``nearest_nodes`` needs scikit-learn to search an unprojected
    graph; for the handful of clicked points we route through, a direct numpy
    scan is simpler and dependency-free. Longitude is scaled by cos(lat) so the
    comparison is not distorted by the meridian convergence at this latitude.
    """
    node_ids = list(graph.nodes)
    xs = np.fromiter((graph.nodes[n]["x"] for n in node_ids), dtype=float, count=len(node_ids))
    ys = np.fromiter((graph.nodes[n]["y"] for n in node_ids), dtype=float, count=len(node_ids))
    cos_lat = math.cos(math.radians(point.lat))
    dx = (xs - point.lon) * cos_lat
    dy = ys - point.lat
    return node_ids[int(np.argmin(dx * dx + dy * dy))]


def route_nodes(
    graph,
    start: LatLon,
    finish: LatLon,
    waypoints: list[LatLon] | None = None,
) -> list[int]:
    """Return the ordered list of graph node ids for start -> ... -> finish.

    Each clicked point is snapped to its nearest node, then consecutive pairs are
    joined by the shortest path. Waypoints let the caller force the true line
    where the shortest path would otherwise deviate from the road actually taken.
    """
    sequence = [start, *(waypoints or []), finish]
    node_ids = [_nearest_node(graph, p) for p in sequence]

    full: list[int] = []
    for origin, dest in zip(node_ids[:-1], node_ids[1:]):
        leg = ox.routing.shortest_path(graph, origin, dest, weight="length")
        if leg is None:
            raise RouteNotFound(origin, dest)
        if full and full[-1] == leg[0]:
            full.extend(leg[1:])
        else:
            full.extend(leg)
    return full


def _dist2(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def route_linestring(graph, route: list[int]) -> LineString:
    """Stitch a node route into one WGS84 LineString following real road curves.

    For each traversed edge we prefer its stored ``geometry`` (the curved shape
    of the way); where absent we fall back to a straight segment between nodes.
    Edge geometries are oriented to the OSM way's direction, which may be
    opposite to our travel direction, so each edge is flipped if its first vertex
    is farther from the ``u`` node than its last.
    """
    coords: list[tuple[float, float]] = []
    for u, v in zip(route[:-1], route[1:]):
        edges = graph.get_edge_data(u, v)
        edge = min(edges.values(), key=lambda d: d.get("length", math.inf))

        geom = edge.get("geometry")
        if geom is not None:
            pts = list(geom.coords)
        else:
            pts = [
                (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                (graph.nodes[v]["x"], graph.nodes[v]["y"]),
            ]

        u_pt = (graph.nodes[u]["x"], graph.nodes[u]["y"])
        if _dist2(pts[0], u_pt) > _dist2(pts[-1], u_pt):
            pts.reverse()

        if coords and coords[-1] == pts[0]:
            coords.extend(pts[1:])
        else:
            coords.extend(pts)

    return LineString(coords)


class RouteNotFound(RuntimeError):
    """Raised when no path connects two snapped points on the road graph."""

    def __init__(self, origin: int, dest: int) -> None:
        super().__init__(
            f"No route between nodes {origin} and {dest}. "
            "The points may be on disconnected road networks, or the download "
            "area was too small to connect them."
        )
