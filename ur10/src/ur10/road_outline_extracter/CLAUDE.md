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
   simplify) → `ExtractedRoad`. The Roads tab then samples an **elevation
   profile** (`elevation.py`) to fill `elevation_loss_m` + `max_grade_pct`,
   best-effort (see below).
2. **Plot** (`layout.plan`): `ExtractedRoad.line_utm` + `PlotConfig` → rotate →
   fit-to-canvas (rotation-aware, into the largest label-free rectangle when a
   label is present) → place (center + nudge) → multi-stroke parallel offsets →
   `PlotResult.strokes` → `svg.render` (flip to SVG y-down, millimeter units) →
   SVG string.

### Modules
- `models.py` — `LatLon` (`.parse()` for "lat, lon" text), `ExtractedRoad`,
  `PlotConfig`, `LabelConfig`, `RoadMetadata`, `RoadRun`.
- `osm.py` — OpenStreetMap graph download + routing + centerline stitching.
- `geometry.py` — projection (WGS84 ↔ UTM), trim-to-endpoints, simplify.
- `pipeline.py` — thin orchestration over osm + geometry.
- `elevation.py` — samples a DEM (free key-less **Open-Topo-Data** API, SRTM
  ~30 m, over stdlib `urllib` — no extra dependency) at each vertex, then derives
  **total descent** (`elevation_loss_m`) and **steepest grade** (`max_grade_pct`).
  The DEM profile is metre-quantized and unevenly spaced, so a 1 m step over a 5 m
  vertex gap reads as a 20% grade (and inflates the descent too). Both stats are
  therefore computed on a *cleaned* profile: resampled to the DEM resolution
  (`SAMPLE_STEP_M`), smoothed to kill the quantization (`SMOOTH_WINDOW_M`, scaled
  down on short roads so it can't swallow their real drop), with grade measured
  over a `GRADE_WINDOW_M` baseline — finer than that, ~30 m SRTM has no signal.
  Best-effort: the tab catches any failure so a flaky service never blocks an
  extraction. Stats persist in `centerline.geojson` properties (like `length_m`).
- `layout.py` — plotting-stage transforms, all in **paper millimeters, y-up**.
  Fits the road into the largest label-free rectangle (`_largest_free_fit`, an
  exact maximal-empty-rectangle scan over the obstacle/canvas cut-lines) when
  `plan`/`place_centerline` are given the label's `obstacles`.
- `label.py` — optional metadata label. The **nickname** is a title pinned to
  the **canvas top-center** (+2 mm); the rest form an anchored, nudgeable block:
  **real name** / **road length** / **start + finish coords on one row** /
  **date**. Any field toggles off. Emits
  single-stroke Hershey text (via vpype) as `LineString`s in the **same y-up mm
  space** as the road, so it merges straight into the stroke list. Three steps:
  `build_rows` (per-line text/size spec) -> `render_rows` (per-row vpype
  geometry; expensive, cached by the tab on rows+font) -> `place_rows` (stack +
  anchor + flip; cheap, re-run on every position/nudge/spacing edit).
- `compass.py` — optional minimal north compass (a symmetric rhombus needle + a
  3-stroke "N", no ring) pinned to the bottom-right corner. Pure geometry, no
  font. Its needle points to
  `(-sin θ, cos θ)` in the y-up frame, i.e. where north lands after `layout`
  rotates the road CCW by `rotation_deg`, so it stays truthful under any rotation.
  Emits `LineString`s in the same y-up mm space, merged into the stroke list.
- `svg.py` — millimeter SVG emission (flips y-up → SVG y-down).
- `storage.py` — `roads/<slug>/` load/save, `slugify`, `road_dir`, `list_roads`.

### UI
The UI is the DPG **Roads** tab, [../app/tab_roads.py](../app/tab_roads.py)
(extract fields + saved-runs + plot controls + Save / Send to UR10). The old
Streamlit `app.py` / `extract_page.py` / `plot_page.py` were removed on
integration; the interactive click-map was replaced by coordinate entry + a
Paste button.

## Key decisions

- **Shape**: **centerline only** — ribbon/outline was considered and **dropped**:
  at real road scale the drawing is zoomed so far out that a curb-width ribbon is
  visually indistinguishable from the centerline, so it adds complexity for no
  visible payoff. Centerline-only is the intended final design.
- **Sizing**: **fit-to-canvas**, rotation-aware; canvas W/H is a user input.
- **Boldening**: `stroke_count` parallel passes spaced `stroke_offset_mm`
  (default 0.65, just under the 0.7 mm pen so passes overlap into a solid line).
- **Metadata** (real name, nickname, date, coords) is stored and can be
  **optionally plotted** as a single-stroke Hershey label (`label.py` +
  `LabelConfig`): the nickname is a top-center title (+2 mm); the rest are an
  anchored, nudgeable block (real name / road length / coords-on-one-row / date).
  Pick which fields to show, plus font, size, line spacing, corner anchor, and
  x/y nudge. Off by default; distance is a derived extra line.
- **North compass** (`compass.py` + `LabelConfig.compass_*`): an optional
  symmetric-diamond needle + "N" (no ring) in the bottom-right corner, whose
  needle tracks `rotation_deg` so north stays truthful when the road is spun to
  fit. Off by default.
- **Capture**: two points (start + finish) — **not** multi-waypoint (see the
  "not wanted" note under Future work); in PLOTTUR10 entered as `lat, lon` (with
  a Paste button), replacing the original click-on-map.

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

- A poster/gallery composing multiple runs with labels.
- GPX import + map-matching.
- (Explicitly **not** wanted: multi-waypoint routes — start+finish only.)

## Dependencies

Runtime: `osmnx`, `geopandas`, `pyproj`, `shapely`, `numpy` (<2), plus `vpype`
(only `label.py`, for Hershey text — the same dependency the vectorizer/Text tabs
already use; imported lazily). Elevation (`elevation.py`) adds **no** dependency —
it calls the Open-Topo-Data HTTP API over stdlib `urllib`. Shared with the parent app; no separate install.
Python ≥ 3.11, managed by Poetry at the ur10 project level.
