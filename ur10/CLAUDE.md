# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A desktop GUI application that turns a raster image into a physical pen drawing made by a **UR10 robot arm**. The robot's end effector holds a **spring-loaded pen**, so pen-to-surface contact is maintained even on uneven mounting surfaces.

The full pipeline is:

1. **Vectorize** an image into line art (a vpype `Document`) using one of several methods.
2. **Save** that as an SVG.
3. In the **UR10 Control** tab, load the SVG, set a physical home/origin, and **stream** the drawing to the robot as real-time `moveL` motion commands.

The app is a single `FreeSimpleGUI` (PySimpleGUI fork) window with tabs: Flow Imager, Hatched, Dither, Text, UR10 Control, and Instructions.

## Running & tooling

Dependencies are managed with **Poetry** (`pyproject.toml`, `poetry.lock`); a `.venv` is present. Python 3.11–3.13.

**Run the app from the project root** (`ur10/`, the directory containing `home_config.json`):

```bash
python src/ur10/ur10_plotter_gui.py
```

This working directory matters for two reasons:
- Module imports inside `src/ur10/` are **flat, not package-relative** (e.g. `from gui_layout import ...`, `from robot.ur10_controller import ...`). They resolve because running the script puts `src/ur10/` on `sys.path[0]`.
- `home_config.json` is read/written with a **relative path**, so it is found only when CWD is the project root.

Lint with ruff (the only dev dependency):

```bash
poetry run ruff check .
```

There is **no test suite** — `tests/` contains only an empty `__init__.py`. The `[tool.poetry] packages` entry declares `ur10` from `src`, but the app is normally run as a script (above), not imported as an installed package.

## Architecture

### Two-stage data flow

The core mental model is **image → vpype Document → SVG file → robot poses → motion stream**. The vectorizer tabs only produce SVGs; the UR10 tab consumes an SVG independently. They are decoupled by the SVG file on disk.

- [src/ur10/ur10_plotter_gui.py](src/ur10/ur10_plotter_gui.py) — the entry point and the single central event loop. It owns all application state (the per-tab vpype documents, `home_pose`, the `UR10Controller` instance) and dispatches every button/event. This is the file to read first.
- [src/ur10/gui_layout.py](src/ur10/gui_layout.py) — `create_layout()` builds the entire window and defines every widget `-KEY-`. The event loop keys must stay in sync with this file.
- [src/ur10/gui_preview.py](src/ur10/gui_preview.py) — renders vpype `Document`s to preview images using a headless Matplotlib (`Agg`) backend. CMYK layers 1–4 map to cyan/magenta/yellow/black.

### Vectorizers (`src/ur10/vectorizers/`)

Each produces a `vpype.Document`. They share a convention: work happens off the GUI thread and results/logs come back via `window.write_event_value(...)` events (`-LOG_MESSAGE-`, `-THREAD_DONE-`), which the main loop handles.

- **flow** ([flow_vectorizer.py](src/ur10/vectorizers/flow_vectorizer.py)) — shells out to vpype's `flow_img` command (from `vpype-flow-imager`). The GUI assembles the command string.
- **hatched** ([hatched_vectorizer.py](src/ur10/vectorizers/hatched_vectorizer.py)) — uses the bundled [src/ur10/hatched.py](src/ur10/hatched.py) library (contours + diagonal/circular hatching via shapely/skimage/OpenCV).
- **dither** ([dither_vectorizer.py](src/ur10/vectorizers/dither_vectorizer.py)) — Floyd-Steinberg / ordered / stochastic dithering into dots. Optional CMYK separation with GCR.

**Threading/termination pattern (important):** Flow and Dither run their heavy work in a **separate `multiprocessing.Process`** (not just a thread) so the user's Stop button can forcibly `terminate()`/`kill()` it. The child returns its result by writing a temp `.svg` and passing the path back through a `multiprocessing.Queue`; the parent re-reads it via vpype. Hatched instead runs in a plain thread and stops **cooperatively** by checking a `threading.Event` (`stop_event`).

### Dither dots quirk

Dithered output is stored as tiny **closed circle polygons** (so it previews as filled dots). Before saving or optimizing, [dither_converter.py](src/ur10/dither_converter.py) `_convert_dither_circles_to_points()` collapses each circle to a **zero-length line** at its centroid, so the robot receives point/dot commands rather than tracing circles. The UR10 tab's "Render SVG as dots" checkbox switches preview and drawing to this dot interpretation.

### Robot control (`src/ur10/robot/`)

- [robot/svg_parser.py](src/ur10/robot/svg_parser.py) — `parse_svg()` is the geometry brain. It reads `<path>`, `<polyline>`, `<polygon>`, `<line>`; scales the SVG (using `viewBox` or width/height, falling back to computed bounds) to fit the canvas in **mm** preserving aspect ratio; then converts to robot poses in **meters**. Key transforms, in order:
  - Corner origin logic (`Top/Bottom Left/Right`, `Center`) positions the drawing relative to `home_pose`.
  - The robot **Y-axis is inverted** relative to SVG Y.
  - A **global rotation** is applied around the home point — note the baked-in `rotation_angle + 45` offset used consistently in `parse_svg`, `-DRAW_LINE-` un-rotation, and `Check Canvas`. The GUI default rotation is `90`.
  - Returns `(list_of_paths, scaled_width_m, scaled_height_m)`, where each path is a list of `(x, y, z, rx, ry, rz)` poses.
- [robot/ur10_controller.py](src/ur10/robot/ur10_controller.py) — `UR10Controller` wraps `ur_rtde` (`rtde_control` / `rtde_receive`). `execute_path_realtime()` streams the paths with `moveL`, handling pen-up/pen-down, pause, and stop via `threading.Event`s, and emits `-DRAW_LINE-` events so the GUI can draw the live preview.

**Z-height model:** `home_pose` (persisted in `home_config.json`) is the pose with the **pen touching the canvas** — i.e. the drawing Z. Two module-level offsets in `ur10_controller.py` define everything else: `SAFE_Z_OFFSET` (10 mm) is the pen-up / "home" travel height, and `PEN_CHANGE_Z_OFFSET` (200 mm) is the pen-swap height. A **Dry Run** just draws at the safe Z so nothing touches the surface.

### Persisted config

`home_config.json` stores `{"pose": [...6 values...], "corner": "..."}`. It is written by "Set Home to Current Position" and loaded at startup.

## Legacy / non-package code (do not treat as current)

- `other/*_v1.2.py` — the original standalone scripts (`vpype_gui_v1.2.py`, `dither_v1.2.py`, etc.) that were refactored into the `src/ur10/` package. Kept for reference only.
- [src/ur10/robot_control/ur10_svg_interpreter.py](src/ur10/robot_control/ur10_svg_interpreter.py) — an old experimental standalone script (also targets an FR5 robot via `frrpc`, which is **not** a project dependency). Not part of the GUI app.
- `README.md` is **out of date**: it references entry points (`ur10_plotter_gui_v1.0.0.py`, `vpype_gui_v1.2.py`) that no longer exist as described. Prefer this file for how to run.
</content>
</invoke>