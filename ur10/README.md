# UR10 Plotter

Turn an image into a physical pen drawing made by a **UR10 robot arm**. The robot's end effector holds a **spring-loaded pen**, so contact with the drawing surface is maintained even when the mounting surface is uneven.

The workflow is:

1. **Vectorize** an image into line art using one of several methods.
2. **Save** the result as an SVG.
3. In the **UR10 Control** tab, load the SVG, set a physical home/origin, and **stream** the drawing to the robot as real-time motion commands.

## Requirements

- Python 3.11–3.13
- [Poetry](https://python-poetry.org/) for dependency management
- A UR10 robot reachable over the network (for actual plotting)

## Installation

```bash
poetry install
```

Key dependencies (see `pyproject.toml` for the full list): `freesimplegui`, `vpype`, `vpype-flow-imager`, `cairosvg`, `reportlab`, `matplotlib`, `numpy`, `ur-rtde`, `svg.path`.

## Running

Run from the **project root** (the directory containing `home_config.json`):

```bash
python src/ur10/ur10_plotter_gui.py
```

> The working directory matters: internal imports resolve against `src/ur10/`, and `home_config.json` is read/written with a relative path, so it is only found when the current directory is the project root.

## The application

The app is a single window with the following tabs:

### Vectorizer tabs

Each vectorizer produces an SVG that the robot can plot. Long-running vectorization happens off the UI thread and can be cancelled with the **Stop** button.

- **Flow Imager** — Uses vpype's `flow_img` (from `vpype-flow-imager`) to create vector fields that follow the dark areas of an image, producing a "flow" effect.
- **Hatched** — Uses the bundled `hatched.py` library to represent shading with diagonal or circular hatch lines (plus optional contours).
- **Dither** — Converts an image into a field of dots using Floyd-Steinberg, ordered (halftone), or stochastic dithering. Supports optional CMYK separation for multi-pen plotting.
- **Text** — Lays out plotter-friendly single-stroke (Hershey) text as an SVG.

Each vectorizer tab also offers **Optimize** (vpype `linemerge` / `linesimplify` / `linesort`) and **Save SVG**. See the **Instructions** tab in the app for a description of every parameter.

### UR10 Control tab

Loads an SVG and drives the robot. Controls:

- **Robot IP** — The IP address of the UR10 robot.
- **Connect to UR10** — Connects to the robot at the specified IP address.
- **SVG File** — The SVG file to be plotted.
- **Render SVG as dots** — Interpret the SVG as dots (use this for dithered files).
- **Set Home to Current Position** — Move the robot so the pen is touching the canvas corner, then set this as the "drawing Z-height". Travel moves happen 10mm above this point.
- **Canvas Corner** — The corner of the canvas to use as the origin.
- **Global Rotation** — Rotates the drawing about the home point before plotting.
- **Canvas Width / Height (mm)** — The target canvas size; the SVG is scaled to fit while preserving aspect ratio.
- **Plotting Speed / Acceleration** — Motion parameters (m/s and m/s²).
- **Dry Run** — If checked, the robot stays at the safe travel height (10mm above the canvas) so the pen never touches the surface.
- **Start Plotting** — Parses the SVG and begins streaming the drawing to the robot.
- **Pause / Resume** — Lifts the pen and returns home; press again to resume from where it left off.
- **Stop** — Stops plotting and returns the robot to its home position.
- **Go Home** — Moves the robot to the safe home position (10mm above the canvas).
- **Pen Change** — Moves the robot to a safe pen-swap position (200mm above the canvas).
- **Check Canvas** — Traces the canvas perimeter at the safe height so you can verify placement before drawing.

The **Real-time Drawing** preview shows the plot as the robot draws it.

### Home position

"Set Home to Current Position" writes the pen-on-canvas pose and selected corner to `home_config.json`, which is reloaded at startup. This pose defines the drawing Z-height; the safe travel height (10mm) and pen-change height (200mm) are offsets above it.

## Project layout

```
src/ur10/
  ur10_plotter_gui.py     # Entry point + central event loop
  gui_layout.py           # Window and all widget definitions
  gui_preview.py          # Matplotlib-based previews
  hatched.py              # Bundled hatching library
  dither_converter.py     # Circle-polygon -> dot conversion
  text_object.py
  vectorizers/            # flow / hatched / dither vectorizers
  robot/
    svg_parser.py         # SVG -> scaled robot poses
    ur10_controller.py    # ur_rtde motion control
```

`other/` contains the original standalone v1.2 scripts that were refactored into this package, kept for reference only.
</content>