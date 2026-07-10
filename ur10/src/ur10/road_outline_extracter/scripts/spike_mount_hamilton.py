"""Phase 1 validation spike: extract Mount Hamilton (Lick Observatory -> Smith Creek).

Runs the whole extraction pipeline headlessly on a known road:

    download graph -> route -> stitch centerline -> project -> trim -> simplify

and writes two artifacts under roads/<slug>/ for inspection:

    centerline.geojson  the extracted centerline (WGS84)
    preview.png         the centerline drawn over the local road network

Run with:  poetry run python scripts/spike_mount_hamilton.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# parents[2] = src/ur10 (so `import road_outline_extracter` resolves as a flat module,
# like robot/ and vectorizers/); parents[4] = the ur10 project root that holds roads/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

import matplotlib

matplotlib.use("Agg")  # headless: render straight to PNG, no GUI window

import osmnx as ox

from road_outline_extracter import geometry, osm
from road_outline_extracter.models import LatLon

# Endpoints resolved from OpenStreetMap (authoritative, not hand-typed).
START = LatLon(lat=37.3415325, lon=-121.6429004)  # Lick Observatory Visitor Center
FINISH = LatLon(lat=37.3225748, lon=-121.6691500)  # Cal Fire Smith Creek Fire Station 12

SLUG = "mount-hamilton-lick-to-smith-creek"
OUT_DIR = _PROJECT_ROOT / "roads" / SLUG


def _write_geojson(road, path: Path) -> None:
    feature = {
        "type": "Feature",
        "properties": {
            "slug": SLUG,
            "length_m": round(road.length_m, 1),
            "n_points": road.n_points,
            "utm_epsg": road.utm_epsg,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[x, y] for x, y in road.line_wgs84.coords],
        },
    }
    path.write_text(json.dumps(feature, indent=2))


def _write_preview(graph, road, path: Path) -> None:
    fig, ax = ox.plot_graph(
        graph,
        show=False,
        close=False,
        node_size=0,
        edge_color="#d9d9d9",
        edge_linewidth=0.7,
        bgcolor="white",
    )
    xs, ys = road.line_wgs84.xy
    ax.plot(xs, ys, color="#e6194b", linewidth=2.2, zorder=4, label="extracted road")
    ax.scatter([START.lon], [START.lat], c="#2ca02c", s=55, zorder=5, label="drop-in")
    ax.scatter([FINISH.lon], [FINISH.lat], c="#1f77b4", s=55, zorder=5, label="finish")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    fig.savefig(path, dpi=150, bbox_inches="tight")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading road network around {SLUG} ...")
    graph = osm.download_graph([START, FINISH], network_type="drive")
    print(f"  graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    print("Routing start -> finish ...")
    route = osm.route_nodes(graph, START, FINISH)
    line_wgs84 = osm.route_linestring(graph, route)
    print(f"  routed centerline: {len(line_wgs84.coords)} raw vertices")

    print("Projecting, trimming to exact endpoints, simplifying ...")
    road = geometry.extract_centerline(line_wgs84, START, FINISH, simplify_tolerance_m=1.0)

    length_km = road.length_m / 1000
    print("\n=== Extracted road ===")
    print(f"  length      : {road.length_m:,.0f} m  ({length_km:.2f} km / {length_km * 0.621:.2f} mi)")
    print(f"  vertices    : {road.n_points}")
    print(f"  UTM zone    : EPSG:{road.utm_epsg}")

    geojson_path = OUT_DIR / "centerline.geojson"
    preview_path = OUT_DIR / "preview.png"
    _write_geojson(road, geojson_path)
    _write_preview(graph, road, preview_path)

    print("\nWrote:")
    print(f"  {geojson_path}")
    print(f"  {preview_path}")


if __name__ == "__main__":
    main()
