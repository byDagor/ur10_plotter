# CLAUDE.md — road_outline_extracter module

Context for the road-extraction module. This began as a standalone Streamlit app;
it is now an **integrated module of PLOTTUR10**, driven by the DPG **Roads** tab
([../app/tab_roads.py](../app/tab_roads.py)). The logic modules here are
framework-agnostic and were reused unchanged; only the Streamlit UI was dropped.
See the parent [../../../CLAUDE.md](../../../CLAUDE.md) ("Roads tab") for how it
plugs into the app and hands SVGs to the robot.

## What this is

Turns real-world roads (e.g. ones the user has longboarded) into plotter-ready,
millimeter-accurate SVGs. The plotter is the UR10 arm, so canvas size is always a
free user parameter, never hardcoded.

## Architecture: two stages

**Extract once, plot many ways.** Geometry capture is separate from layout.

1. **Extract** (`pipeline.extract_road`): `LatLon` points →
   `osm.download_graph` → `osm.route_nodes` → `osm.route_linestring` (WGS84) →
   `geometry.extract_centerline` (project to UTM, trim to the exact endpoints,
   simplify) → `ExtractedRoad`.
2. **Plot** (`layout.plan`): `ExtractedRoad.line_utm` + `PlotConfig` → rotate →
   fit-to-canvas (rotation-aware) → place (center + nudge) → multi-stroke
   parallel offsets → `PlotResult.strokes` → `svg.render` (flip to SVG y-down,
   millimeter units) → SVG string.

### Modules
- `models.py` — `LatLon` (`.parse()` for "lat, lon" text), `ExtractedRoad`,
  `PlotConfig`, `RoadMetadata`, `RoadRun`.
- `osm.py` — OpenStreetMap graph download + routing + centerline stitching.
- `geometry.py` — projection (WGS84 ↔ UTM), trim-to-endpoints, simplify.
- `pipeline.py` — thin orchestration over osm + geometry.
- `layout.py` — plotting-stage transforms, all in **paper millimeters, y-up**.
- `svg.py` — millimeter SVG emission (flips y-up → SVG y-down).
- `storage.py` — `roads/<slug>/` load/save, `slugify`, `road_dir`, `list_roads`.

### UI
The UI is the DPG **Roads** tab, [../app/tab_roads.py](../app/tab_roads.py)
(extract fields + saved-runs + plot controls + Save / Send to UR10). The old
Streamlit `app.py` / `extract_page.py` / `plot_page.py` were removed on
integration; the interactive click-map was replaced by coordinate entry + a
Paste button.

## Key decisions

- **Shape**: **centerline only** (ribbon/outline is planned future work below).
- **Sizing**: **fit-to-canvas**, rotation-aware; canvas W/H is a user input.
- **Boldening**: `stroke_count` parallel passes spaced `stroke_offset_mm`
  (default 0.65, just under the 0.7 mm pen so passes overlap into a solid line).
- **Metadata** (nickname, real name, date, coords) is **stored, not plotted**.
- **Capture**: two points (start + finish); in PLOTTUR10 entered as `lat, lon`
  (with a Paste button), replacing the original click-on-map.

## Coordinate-system rule (important)

WGS84 (degrees) is the **canonical stored geometry** (`centerline.geojson`). All
metric math — trimming, simplify tolerance, pen offsets, scaling — happens on the
**projected UTM line** (`ExtractedRoad.line_utm`), never on raw lat/lon. On load,
geometry is reprojected to the stored EPSG.

## Gotchas (already handled — don't re-break)

- **osmnx 2.1.0 `simplify=True` collapses sparse rural drive graphs to 1 node.**
  `osm.download_graph` uses `simplify=False` (also gives full-resolution curves).
- **Nearest node** is a small numpy scan in `osm._nearest_node` — deliberately
  avoids osmnx's `nearest_nodes`, which needs scikit-learn on unprojected graphs.
- **SVG y-flip**: `layout` works y-up (map convention); `svg.render` flips to
  y-down so north is up on paper.
- **`<path>` output**: `svg.render` emits `<path>` (M/L). The robot's `parse_svg`
  had a latent `<path>` bug (it called `svgpathtools`' `continuous_subpaths()` on
  a `svg.path` object) that these SVGs surfaced and fixed — see the parent
  CLAUDE.md.

## Running & validating

Run via the parent app (Roads tab): `.venv/Scripts/python.exe src/ur10/plottur10.py`
from the `ur10/` project root. The extract stage needs internet (OSM); saved runs
re-plot offline.

- **Spikes** in `scripts/` (`spike_mount_hamilton.py`, `spike_plot_mount_hamilton.py`)
  run the pipeline end-to-end and write preview PNGs. They add `src/ur10` to
  `sys.path` and write under the project-root `roads/`.
- **Tests** in `tests/` (storage round-trip, `LatLon.parse`) need `pytest` (not
  currently a project dep); a `conftest.py` puts `src/ur10` on the path.
- **Canonical test road**: Mount Hamilton, CA.
  - Lick Observatory (drop-in): `37.3415325, -121.6429004`
  - Cal Fire Smith Creek Fire Station 12 (finish): `37.3225748, -121.6691500`
  - Expected extract: ~10.14 km, ~536 points, EPSG:32610.
  - Saved under `roads/mount-hamilton-lick-to-smith-creek/`.

## Possible future work (none committed)

- Ribbon/outline mode (buffer the centerline to road width — a superset of
  centerline; this is the "outline" the module name promises).
- Plotting the metadata as text (single-line/Hershey font).
- A poster/gallery composing multiple runs with labels.
- GPX import + map-matching.

## Dependencies

Runtime: `osmnx`, `geopandas`, `pyproj`, `shapely`, `numpy` (<2). Shared with the
parent app; no separate install. Python ≥ 3.11, managed by Poetry at the ur10
project level.
