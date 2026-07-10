# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A desktop GUI application that turns a raster image into a physical pen drawing made by a **UR10 robot arm**. The robot's end effector holds a **spring-loaded pen**, so pen-to-surface contact is maintained even on uneven mounting surfaces.

The full pipeline is:

1. **Vectorize** an image into line art (a vpype `Document`) using one of several methods.
2. **Save** that as an SVG.
3. In the **UR10 Control** tab, load the SVG, set a physical home/origin, and **stream** the drawing to the robot as real-time `moveL` motion commands.

The app is a single **Dear PyGui** window with tabs: Flow Imager, Hatched, Dither, Text, Roads, UR10 Control, and Instructions.

The **Roads** tab is a second front-end to step 1: instead of vectorizing an image, it extracts a real road's centerline from OpenStreetMap and lays it out as a millimeter SVG (see the **Roads tab** section under Architecture). Steps 2–3 are unchanged — it produces an SVG the UR10 tab consumes like any other.

## Running & tooling

Dependencies are managed with **Poetry** (`pyproject.toml`, `poetry.lock`); a `.venv` is present. Python 3.11–3.13. The Roads tab adds `osmnx` / `geopandas` / `pyproj` (resolved against the `numpy<2` pin — they slot in without disturbing it).

The app is built with **Dear PyGui**. Entry point:

```bash
python src/ur10/plottur10.py
```

Use the project virtualenv interpreter for commands — on Windows that's `.venv/Scripts/python.exe` (e.g. `.venv/Scripts/python.exe src/ur10/plottur10.py`). Run from the project root (`ur10/`, the directory containing `home_config.json`). The working directory matters for two reasons:
- Module imports inside `src/ur10/` are **flat, not package-relative** (e.g. `from robot.ur10_controller import ...`, `from app.main import main`). They resolve because `plottur10.py` puts `src/ur10/` on `sys.path[0]`.
- `home_config.json` is read/written with a **relative path**, so it is found only when CWD is the project root.

Quick build check without clicking through the UI: `DPG_SMOKE_TEST=1 python src/ur10/plottur10.py` builds every tab, renders a few frames, prints `SMOKE TEST OK`, and exits. Use it after edits to catch import/layout errors. (It still opens a viewport, so it needs a display session.)

Lint with ruff (the only dev dependency):

```bash
poetry run ruff check .
```

There is **no test suite** — `tests/` contains only an empty `__init__.py`. The `[tool.poetry] packages` entry declares `ur10` from `src`, but the app is normally run as a script (above), not imported as an installed package.

## Architecture

### Two-stage data flow

The core mental model is **image → vpype Document → SVG file → robot poses → motion stream**. The vectorizer tabs only produce SVGs; the UR10 tab consumes an SVG independently. They are decoupled by the SVG file on disk. The view layer that drives all of this is the `app/` package (**see [Dear PyGui front-end](#dear-pygui-front-end-srcur10app) below — read that first**); the image-processing and robot logic sit in the framework-agnostic modules (`vectorizers/`, `robot/`, `hatched.py`, `dither_converter.py`, `text_object.py`), which the view layer reuses unchanged.

### Vectorizers (`src/ur10/vectorizers/`)

Each produces a `vpype.Document`. They share a convention: work happens off the UI thread and results/logs come back via `window.write_event_value(...)` events (`-LOG_MESSAGE-`, `-THREAD_DONE-`) — where `window` is an `EventBridge` (see `app/bridge.py`) that marshals those events onto the main thread.

- **flow** ([flow_vectorizer.py](src/ur10/vectorizers/flow_vectorizer.py)) — shells out to vpype's `flow_img` command (from `vpype-flow-imager`). The GUI assembles the command string.
- **hatched** ([hatched_vectorizer.py](src/ur10/vectorizers/hatched_vectorizer.py)) — uses the bundled [src/ur10/hatched.py](src/ur10/hatched.py) library (contours + diagonal/circular hatching via shapely/skimage/OpenCV).
- **dither** ([dither_vectorizer.py](src/ur10/vectorizers/dither_vectorizer.py)) — Floyd-Steinberg / ordered / stochastic dithering into dots. Optional CMYK separation with GCR.

**Threading/termination pattern (important):** Flow and Dither run their heavy work in a **separate `multiprocessing.Process`** (not just a thread) so the user's Stop button can forcibly `terminate()`/`kill()` it. The child returns its result by writing a temp `.svg` and passing the path back through a `multiprocessing.Queue`; the parent re-reads it via vpype. Hatched instead runs in a plain thread and stops **cooperatively** by checking a `threading.Event` (`stop_event`).

### Dither dots quirk

The dither vectorizer emits tiny **closed circle polygons** as its transport format (it must — the dither subprocess returns its result via a temp SVG, and vpype's reader drops zero-length points). [dither_converter.py](src/ur10/dither_converter.py) `_convert_dither_circles_to_points()` collapses each circle to a **zero-length line** at its centroid, so the robot receives point/dot commands rather than tracing circles. In the app the Dither tab does this collapse on receipt (grayscale), so preview/save/plot are all dots; the UR10 tab auto-detects dithered SVGs (mostly zero-length geometry) and renders them as dots without any toggle.

### Roads tab (`src/ur10/road_outline_extracter/`)

A second SVG source: draw a **real-world road** extracted from OpenStreetMap (relocated + de-Streamlit'd from a standalone project; the logic modules are framework-agnostic and reused as-is, wrapped by [app/tab_roads.py](src/ur10/app/tab_roads.py) in the same DPG idioms as the vectorizer tabs). **Extract once, plot many ways** — two stages:

1. **Extract** (`pipeline.extract_road`): two `lat, lon` points → `osm` downloads the local road graph and routes between them → `geometry` projects to UTM, trims to the exact endpoints, simplifies → `ExtractedRoad`. Only this stage needs the network; **osmnx is imported lazily** inside the extract worker so startup doesn't pay for it. Runs off-thread via the tab's `EventBridge` (`-ROADS_DONE-`), like a vectorizer (plain daemon thread — no process kill).
2. **Plot** (`layout.plan`): `ExtractedRoad.line_utm` + `PlotConfig` → rotate → fit-to-canvas (rotation-aware) → center + nudge → `stroke_count` parallel passes (bolding) → `svg.render` emits a **millimeter** SVG (`<path>` M/L, `viewBox` in mm). Pure and fast, so the preview replots live on each control edit.

**Handoff:** "Send to UR10" writes `road_for_ur10.svg` at the project root, sets the UR10 tab's canvas W/H to the road's true size, previews it, and switches to the UR10 tab — the SVG then flows through `parse_svg` unchanged.

**Preview convention:** strokes are flipped to y-down mm exactly as `svg.render` writes them (`canvas_h - y`) and drawn with `flip_y=False`, plus a canvas-border rectangle, so the preview matches the saved SVG and the robot output.

**Storage / UX:** runs persist under `roads/<slug>/` (WGS84 `centerline.geojson` + `meta.json` + `plot.json`); the tab passes an explicit `base_dir` so it doesn't depend on CWD. Three example runs are committed (canonical: Mount Hamilton). Coordinate entry uses a **Paste** button (`dpg.get_clipboard_text()`) — DPG's `input_text` doesn't reliably paste with Ctrl+V, and ImGui has no right-click menu. The module keeps its own [CLAUDE.md](src/ur10/road_outline_extracter/CLAUDE.md) for the geometry details (WGS84-canonical; metric math on the UTM line; osmnx `simplify=False` gotcha).

### Robot control (`src/ur10/robot/`)

- [robot/svg_parser.py](src/ur10/robot/svg_parser.py) — `parse_svg()` is the geometry brain. It reads `<path>`, `<polyline>`, `<polygon>`, `<line>`; scales the SVG (using `viewBox` or width/height, falling back to computed bounds) to fit the canvas in **mm** preserving aspect ratio; then converts to robot poses in **meters**. Key transforms, in order:
  - Corner origin logic (`Top/Bottom Left/Right`, `Center`) positions the drawing relative to `home_pose`.
  - The robot **Y-axis is inverted** relative to SVG Y.
  - A **global rotation** is applied around the home point, computed as `rotation_angle + 45`. The **`+45°` is a physical-mount compensation, not arbitrary**: the robot is mounted **diagonally** to the table, so its base X/Y axes sit at 45° relative to the canvas edges. The `+45` rotates the drawing back into alignment with the physical canvas. The user-facing **Global Rotation** dropdown (default `90`) then orients the drawing on top of that. The same `rotation_angle + 45` expression must stay consistent across `parse_svg`, the `-DRAW_LINE-` preview un-rotation, and `Check Canvas` — changing one without the others will misalign the live preview or canvas check against what the robot actually draws.
  - Returns `(list_of_paths, scaled_width_m, scaled_height_m)`, where each path is a list of `(x, y, z, rx, ry, rz)` poses.
  - **`<path>` handling:** `_get_points_from_element` flattens a path `d` into continuous subpaths (split on `Move`, take `Line` endpoints, sample curves/arcs, honor `Close`). The **Roads** SVGs are the first `<path>` consumer — every vectorizer emits `<polyline>` — which is why this branch had a latent bug (it called `continuous_subpaths()`, a `svgpathtools` method absent from the `svg.path` library) that went unnoticed until roads exercised it.
- [robot/ur10_controller.py](src/ur10/robot/ur10_controller.py) — `UR10Controller` wraps `ur_rtde` (`rtde_control` / `rtde_receive`). `execute_path_realtime()` streams the paths with `moveL`, handling pen-up/pen-down, pause, and stop via `threading.Event`s, and emits `-DRAW_LINE-` events so the GUI can draw the live preview.

**Z-height model:** `home_pose` (persisted in `home_config.json`) is the pose with the **pen touching the canvas** — i.e. the drawing Z. Two module-level offsets in `ur10_controller.py` define everything else: `SAFE_Z_OFFSET` (10 mm) is the pen-up / "home" travel height, and `PEN_CHANGE_Z_OFFSET` (200 mm) is the pen-swap height. A **Dry Run** just draws at the safe Z so nothing touches the surface.

### Dear PyGui front-end (`src/ur10/app/`)

The `app/` package is the DPG view layer behind `plottur10.py` — the entire UI. It reuses all the logic modules unchanged; only rendering and event handling live here.

- [app/main.py](src/ur10/app/main.py) — shell: builds the mode tab bar (Flow / Hatched / Dither / Text / UR10 / Instructions), owns the manual render loop, and each frame calls `bridge.pump_all()` then `canvas.pump_all()` then each tab's `on_frame()`. A viewport-resize callback re-fits every canvas.
- [app/bridge.py](src/ur10/app/bridge.py) — **the key to reuse.** `EventBridge` implements `write_event_value(key, value)` (the FreeSimpleGUI idiom) by enqueuing events; the render loop drains them on the main thread and dispatches to handlers. This is why the vectorizer modules and `UR10Controller.execute_path_realtime` are reused **as-is** — they're handed a bridge where they expect a `window`. Worker threads never touch DPG directly.
- [app/canvas.py](src/ur10/app/canvas.py) — `PreviewCanvas`: a resizable drawlist that caches geometry in *data space* and re-fits on resize; supports incremental `append_item` for animated drawing (demo + live plot). `document_to_items` / `svg_to_items` convert vpype Documents / SVG files to draw items, and `detect_dots` auto-identifies dithered files (>85% zero-length geometry).
- [app/tabbase.py](src/ur10/app/tabbase.py) + [app/vectorizer_tab.py](src/ur10/app/vectorizer_tab.py) — `BaseTab` (uniform sidebar+preview relayout, per-tab log) and `VectorizerTab` (shared vectorize/stop/optimize/save + per-tab `EventBridge`). Each tab is one module (`tab_flow.py`, etc.); the Dither tab collapses the transport circles to center-point dots on receipt (grayscale) via `_transform_document`, exposes a "Reorder for Shortest Travel" button (`linesort` only — merge/simplify are inert on point dots, and raster order wastes ~60% travel), and overrides save for CMYK multi-file export. (The dither subprocess must emit circles, not bare dots, because it returns its result through a temp SVG and vpype's reader drops zero-length points — verified.)

Rendering conventions carried over from the prototype: SVG-space previews use `flip_y=False` (SVG is already Y-down); the UR10 live/demo canvas uses `flip_y=True` (robot Y is inverted). The demo passes `rotation_angle=-45` to `parse_svg` to cancel the diagonal-mount `+45°` and preview upright; the real plot uses the Rotation dropdown so the live canvas mirrors the robot.

### Persisted config

`home_config.json` stores `{"pose": [...6 values...], "corner": "..."}`. It is written by "Set Home to Current Position" and loaded at startup.

## Legacy / non-package code (do not treat as current)

- `other/*_v1.2.py` — the original standalone scripts (`vpype_gui_v1.2.py`, `dither_v1.2.py`, etc.) that predate the `src/ur10/` package. Kept for reference only.
- [src/ur10/robot_control/ur10_svg_interpreter.py](src/ur10/robot_control/ur10_svg_interpreter.py) — an old experimental standalone script (also targets an FR5 robot via `frrpc`, which is **not** a project dependency). Not part of the GUI app.

(The former FreeSimpleGUI front-end — `ur10_plotter_gui.py`, `gui_layout.py`, `gui_preview.py` — was removed once the Dear PyGui app reached parity.)
</content>
</invoke>