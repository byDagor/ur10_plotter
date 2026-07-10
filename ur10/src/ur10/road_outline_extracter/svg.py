"""Emit a plotter-ready SVG from laid-out strokes.

The document is authored in real millimeters: ``width``/``height`` are in mm and
the ``viewBox`` matches, so one SVG user unit equals one millimeter and the
plotter draws at true size. Strokes arrive in y-up (map) coordinates and are
flipped here to SVG's y-down convention so north points up on paper.
"""

from __future__ import annotations

from pathlib import Path

from shapely.geometry import LineString

from .models import PlotConfig


def _path_d(line: LineString, canvas_h_mm: float) -> str:
    coords = list(line.coords)
    commands = []
    for i, (x, y) in enumerate(coords):
        cmd = "M" if i == 0 else "L"
        # flip y: map y-up -> SVG y-down
        commands.append(f"{cmd}{x:.3f},{canvas_h_mm - y:.3f}")
    return " ".join(commands)


def render(strokes: list[LineString], config: PlotConfig) -> str:
    """Render laid-out strokes to an SVG string sized in millimeters."""
    w = config.canvas_w_mm
    h = config.canvas_h_mm

    paths = "\n".join(
        f'  <path d="{_path_d(s, h)}" />'
        for s in strokes
        if len(s.coords) >= 2
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">\n'
        f'  <g fill="none" stroke="black" stroke-width="{config.pen_width_mm}" '
        f'stroke-linecap="round" stroke-linejoin="round">\n'
        f"{paths}\n"
        f"  </g>\n"
        f"</svg>\n"
    )


def write(strokes: list[LineString], config: PlotConfig, path: Path) -> None:
    Path(path).write_text(render(strokes, config))
