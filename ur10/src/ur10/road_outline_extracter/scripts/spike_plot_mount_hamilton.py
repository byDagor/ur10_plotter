"""Phase 2 validation spike: plot the extracted Mount Hamilton road.

Loads the centerline saved by the Phase 1 spike (no network needed), runs the
plotting stage (rotate -> fit -> place -> multi-stroke), writes a plotter SVG,
and renders a validation figure:

    panel 1  the plot at 0 degrees, inside the canvas rectangle
    panel 2  the plot at 30 degrees (proves fit-to-canvas is rotation-aware)
    panel 3  a zoom-in confirming the parallel bold strokes actually appear

Run with:  poetry run python scripts/spike_plot_mount_hamilton.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

# parents[2] = src/ur10 (so `import road_outline_extracter` resolves as a flat module,
# like robot/ and vectorizers/); parents[4] = the ur10 project root that holds roads/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from shapely.geometry import LineString

from road_outline_extracter import geometry, layout, svg
from road_outline_extracter.models import PlotConfig

SLUG = "mount-hamilton-lick-to-smith-creek"
ROAD_DIR = _PROJECT_ROOT / "roads" / SLUG

CONFIG = PlotConfig(
    canvas_w_mm=594,
    canvas_h_mm=841,
    margin_mm=20,
    pen_width_mm=0.7,
    stroke_count=3,
    stroke_offset_mm=0.65,
    rotation_deg=0,
)


def load_centerline_utm() -> LineString:
    data = json.loads((ROAD_DIR / "centerline.geojson").read_text())
    line_wgs84 = LineString(data["geometry"]["coordinates"])
    line_utm, _epsg = geometry.project_line_to_utm(line_wgs84)
    return line_utm


def draw_plot(ax, result: layout.PlotResult, config: PlotConfig, title: str) -> None:
    ax.add_patch(
        Rectangle((0, 0), config.canvas_w_mm, config.canvas_h_mm,
                  fill=False, edgecolor="#999999", linewidth=1)
    )
    for stroke in result.strokes:
        xs, ys = stroke.xy
        ax.plot(xs, ys, color="black", linewidth=0.6)
    ax.set_aspect("equal")
    ax.set_xlim(-20, config.canvas_w_mm + 20)
    ax.set_ylim(-20, config.canvas_h_mm + 20)
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("mm", fontsize=7)


def verify_svg_bounds(result: layout.PlotResult, config: PlotConfig) -> None:
    all_x = [x for s in result.strokes for x in s.xy[0]]
    all_y = [y for s in result.strokes for y in s.xy[1]]
    assert min(all_x) >= -0.5 and max(all_x) <= config.canvas_w_mm + 0.5, "x out of canvas"
    assert min(all_y) >= -0.5 and max(all_y) <= config.canvas_h_mm + 0.5, "y out of canvas"


def main() -> None:
    line_utm = load_centerline_utm()

    result0 = layout.plan(line_utm, CONFIG)
    result30 = layout.plan(line_utm, replace(CONFIG, rotation_deg=30))

    verify_svg_bounds(result0, CONFIG)

    svg_path = ROAD_DIR / "plot.svg"
    svg.write(result0.strokes, CONFIG, svg_path)
    svg_text = svg_path.read_text()
    n_paths = svg_text.count("<path")

    print("=== Plot (0 degrees) ===")
    print(f"  canvas       : {CONFIG.canvas_w_mm} x {CONFIG.canvas_h_mm} mm")
    print(f"  scale        : {result0.scale_mm_per_m:.4f} mm per meter "
          f"({1000 * result0.scale_mm_per_m:.1f} mm per km)")
    print(f"  drawn size   : {result0.draw_w_mm:.1f} x {result0.draw_h_mm:.1f} mm")
    print(f"  strokes      : {len(result0.strokes)} (from stroke_count={CONFIG.stroke_count})")
    print(f"  svg <path>   : {n_paths}")
    print(f"  30deg drawn  : {result30.draw_w_mm:.1f} x {result30.draw_h_mm:.1f} mm")

    # Validation figure.
    fig = plt.figure(figsize=(12, 6))
    ax1 = fig.add_subplot(1, 3, 1)
    ax2 = fig.add_subplot(1, 3, 2)
    ax3 = fig.add_subplot(1, 3, 3)

    draw_plot(ax1, result0, CONFIG, "0 deg  (fit to canvas)")
    draw_plot(ax2, result30, replace(CONFIG, rotation_deg=30), "30 deg  (rotation-aware fit)")

    # Zoom panel: a small window on the centerline to reveal the 3 parallel strokes.
    cx, cy = result0.centerline_mm.coords[len(result0.centerline_mm.coords) // 2]
    for stroke in result0.strokes:
        xs, ys = stroke.xy
        ax3.plot(xs, ys, color="black", linewidth=0.9)
    ax3.set_aspect("equal")
    ax3.set_xlim(cx - 3, cx + 3)
    ax3.set_ylim(cy - 3, cy + 3)
    ax3.set_title(f"zoom: {CONFIG.stroke_count} strokes @ {CONFIG.stroke_offset_mm} mm", fontsize=9)
    ax3.set_xlabel("mm", fontsize=7)

    preview_path = ROAD_DIR / "plot_preview.png"
    fig.tight_layout()
    fig.savefig(preview_path, dpi=150)

    print("\nWrote:")
    print(f"  {svg_path}")
    print(f"  {preview_path}")


if __name__ == "__main__":
    main()
