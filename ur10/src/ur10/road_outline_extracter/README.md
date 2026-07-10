# 🛹 Road Outline Extracter

Turn roads you've longboarded into plotter-ready SVGs. Pick a road on a map,
extract its real centerline from OpenStreetMap, then lay it out on a canvas and
export a millimeter-accurate SVG for a pen plotter.

## What it does

- **Extract** — click a drop-in and a finish on an interactive map (or paste
  Google Maps coordinates). The app downloads the local road network from
  OpenStreetMap, routes along the real road between your two points, trims the
  line to exactly where you clicked, and projects it to meters.
- **Plot** — dial in canvas size, pen width, stroke count, rotation, and
  placement with a live preview. The road is scaled to fit the canvas
  (rotation-aware) and drawn as one or more parallel strokes to bold the line.
- **Export** — save a true-size (millimeter) SVG ready for the plotter.

Each run is saved to its own folder with its geometry, metadata (nickname, real
name, date first skated, coordinates), and last-used plot settings.

## Requirements

- Python ≥ 3.11
- [Poetry](https://python-poetry.org/)

## Install

```sh
poetry install
```

## Run

```sh
poetry run streamlit run app.py
```

This opens a two-page app:

### Extract
1. *(optional)* Paste `lat, lon` from Google Maps into **Jump to coordinates**
   and press **Go** to move the map to your spot.
2. Click your **drop-in** (green), then your **finish** (red).
3. Choose the road network (`drive` for paved roads, `all` to include paths),
   then press **Extract road**. The routed road previews in red.
4. Fill in nickname / real name / date and press **Save run**.

### Plot & export
1. Select a saved run.
2. Adjust canvas, pen, stroke, and placement controls — the preview updates live.
3. **Download SVG** or **Save plot.svg to run folder**.

## Project layout

```
app.py                 Streamlit entry point (st.navigation router)
extract_page.py        Extract page UI
plot_page.py           Plot & export page UI
src/road_outline_extracter/
  models.py            LatLon, ExtractedRoad, PlotConfig, RoadMetadata, RoadRun
  osm.py               download road graph + route between points (OpenStreetMap)
  geometry.py          project to UTM, trim to endpoints, simplify
  pipeline.py          extract_road(): points in, ExtractedRoad out
  layout.py            rotate -> fit-to-canvas -> place -> multi-stroke (paper mm)
  svg.py               emit millimeter SVG
  storage.py           save/load runs under roads/<slug>/
scripts/               validation spikes (Mount Hamilton)
tests/                 pytest suite
roads/                 saved runs (created at runtime)
```

A saved run folder (`roads/<slug>/`) contains:

| File | Contents |
| --- | --- |
| `centerline.geojson` | canonical geometry (WGS84) + length/points/UTM zone |
| `meta.json` | nickname, real name, date first skated, start/finish, created_at |
| `plot.json` | last-used plot settings (`PlotConfig`) |
| `plot.svg` | exported plot |

## Development

```sh
poetry run pytest                                   # run the test suite
poetry run python scripts/spike_mount_hamilton.py   # extract spike (writes a preview PNG)
poetry run python scripts/spike_plot_mount_hamilton.py  # plot spike (writes a preview PNG)
```

The canonical test road is **Mount Hamilton, CA** — Lick Observatory down to the
Cal Fire Smith Creek fire station.
