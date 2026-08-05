"""Elevation profile for an extracted road: descent and steepest grade.

OSM gives us only lat/lon -- the extracted centerline is 2D. To get grade and
elevation loss we sample a digital elevation model (DEM) at each vertex. This
module queries the free, key-less **Open-Topo-Data** public API
(``api.opentopodata.org``, SRTM ~30 m) over stdlib ``urllib`` -- no extra
dependency. It is best-effort: the Roads tab catches any failure so a flaky or
rate-limited elevation service never blocks a road extraction.

Two numbers are derived, both on the *projected UTM* line (metric), the way all
the other road math is (see geometry.py / layout.py):

    total elevation loss  -- sum of every downhill segment (total descent), metres
    highest grade drop    -- steepest sustained descent, %

The DEM profile is noisy: SRTM is ~30 m horizontally and Open-Topo-Data quantizes
elevation to whole metres, while OSM vertices can sit only a few metres apart. A
1 m quantization step over a 5 m gap reads as a 20% grade, and summing every such
wiggle badly overstates the descent too. So both stats are computed on a *cleaned*
profile -- resampled to a uniform grid at the DEM's own resolution, smoothed to
remove the metre-quantization, then measured over a baseline long enough to be
real. Grade finer than that baseline simply isn't recoverable from ~30 m SRTM.
"""

from __future__ import annotations

import json
import math
import time
import urllib.request

from shapely.geometry import LineString

# Public Open-Topo-Data endpoint. SRTM 30 m has global land coverage 60S-60N.
_API_URL = "https://api.opentopodata.org/v1/{dataset}"
_MAX_LOCATIONS = 100  # the public API's per-request cap
_PAUSE_S = 1.0        # the public API allows ~1 request/second

# Profile cleaning + grade baseline. SRTM is ~30 m horizontally and elevation is
# quantized to whole metres, so raw per-vertex grades are dominated by that noise
# (a 1 m step over a 5 m gap = 20%). We resample to the DEM resolution, smooth out
# the quantization, then measure grade over a baseline long enough to be real.
SAMPLE_STEP_M = 30.0      # resample the profile to ~the DEM's horizontal resolution
SMOOTH_WINDOW_M = 120.0   # moving-average span that suppresses metre-quantization
GRADE_WINDOW_M = 90.0     # baseline the steepest grade is measured over

_FEET_PER_M = 3.28084


def fetch_elevations(
    line_wgs84: LineString,
    dataset: str = "srtm30m",
    timeout: float = 30.0,
    _sleep=time.sleep,
) -> list[float]:
    """Elevation (metres) at each vertex of ``line_wgs84`` via Open-Topo-Data.

    Batches the vertices into the API's 100-locations limit, pausing between
    batches to respect the ~1 req/sec public rate. Raises on any network/API
    error (the caller decides whether that is fatal). Any no-data holes the DEM
    returns are filled from their neighbours.
    """
    coords = list(line_wgs84.coords)  # GeoJSON order: (lon, lat)
    raw: list[float | None] = []
    for start in range(0, len(coords), _MAX_LOCATIONS):
        if start:
            _sleep(_PAUSE_S)
        chunk = coords[start:start + _MAX_LOCATIONS]
        locations = "|".join(f"{lat:.6f},{lon:.6f}" for lon, lat in chunk)
        body = json.dumps({"locations": locations}).encode()
        req = urllib.request.Request(
            _API_URL.format(dataset=dataset), data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") != "OK":
            raise RuntimeError(f"elevation API status {data.get('status')!r}")
        raw.extend(r.get("elevation") for r in data["results"])
    return _fill_gaps(raw)


def _fill_gaps(values: list[float | None]) -> list[float]:
    """Replace ``None`` holes (DEM no-data) with the nearest known elevation."""
    if all(v is None for v in values):
        raise RuntimeError("elevation API returned no data for this route")
    filled = list(values)
    last: float | None = None
    for i, v in enumerate(filled):          # forward fill
        if v is None:
            filled[i] = last
        else:
            last = v
    nxt: float | None = None
    for i in range(len(filled) - 1, -1, -1):  # back fill leading holes
        if filled[i] is None:
            filled[i] = nxt
        else:
            nxt = filled[i]
    return [float(v) for v in filled]


def _resample(dist: list[float], elev: list[float],
              step: float) -> tuple[list[float], list[float]]:
    """Linear-interpolate a (distance, elevation) profile onto a uniform grid.

    Uniform spacing is what makes the smoothing and windowing that follow honest:
    raw OSM vertices can be a few metres apart, which turns the metre-quantized DEM
    values into huge spurious grades.
    """
    total = dist[-1]
    grid = []
    x = 0.0
    while x < total:
        grid.append(x)
        x += step
    grid.append(total)

    out = []
    j = 0
    for x in grid:
        while j < len(dist) - 1 and dist[j + 1] < x:
            j += 1
        k = min(j + 1, len(dist) - 1)
        span = dist[k] - dist[j]
        t = (x - dist[j]) / span if span > 0 else 0.0
        out.append(elev[j] + t * (elev[k] - elev[j]))
    return grid, out


def _smooth(values: list[float], step: float, window_m: float) -> list[float]:
    """Centered moving average over ~``window_m`` of a uniformly-spaced series.

    The half-width is capped to ``(len - 1) // 2`` so a window wider than the road
    can't average a short profile into a flat line (which would erase its descent).
    """
    half = min(int(round(window_m / step)) // 2, (len(values) - 1) // 2)
    if half < 1:
        return list(values)
    out = []
    for i in range(len(values)):
        lo, hi = max(0, i - half), min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def elevation_stats(
    line_utm: LineString,
    elevations: list[float],
    grade_window_m: float = GRADE_WINDOW_M,
) -> tuple[float, float]:
    """(total_loss_m, max_grade_pct) from a metric line + per-vertex elevations.

    Both stats are computed on a *cleaned* profile (resampled to a uniform
    ``SAMPLE_STEP_M`` grid, smoothed over ``SMOOTH_WINDOW_M``) so the DEM's
    metre-quantization and uneven vertex spacing don't inflate them.
    ``total_loss_m`` sums the descents; ``max_grade_pct`` is the steepest descent
    over any ``grade_window_m`` stretch (or the whole road if it is shorter).
    Returns (0, 0) if there is nothing to measure.
    """
    coords = list(line_utm.coords)
    n = len(coords)
    if n < 2 or len(elevations) != n:
        return 0.0, 0.0

    dist = [0.0] * n
    for i in range(1, n):
        dist[i] = dist[i - 1] + math.hypot(coords[i][0] - coords[i - 1][0],
                                           coords[i][1] - coords[i - 1][1])
    if dist[-1] <= 0:
        return 0.0, 0.0

    d, z = _resample(dist, elevations, SAMPLE_STEP_M)
    # Scale the smoothing span down on short roads: a fixed ~120 m window would
    # pull a short profile's endpoints toward its mean and swallow its real drop.
    z = _smooth(z, SAMPLE_STEP_M, min(SMOOTH_WINDOW_M, dist[-1] / 2))

    loss = sum(max(0.0, z[i - 1] - z[i]) for i in range(1, len(z)))

    # Steepest descent over a sliding window >= grade_window_m (two pointers on
    # the uniform grid).
    max_grade = 0.0
    j = 1
    for i in range(len(z) - 1):
        if j <= i:
            j = i + 1
        while j < len(z) and d[j] - d[i] < grade_window_m:
            j += 1
        if j >= len(z):
            break
        run = d[j] - d[i]
        if run > 0:
            max_grade = max(max_grade, (z[i] - z[j]) / run * 100.0)

    if max_grade == 0.0:   # road shorter than the window
        max_grade = max(0.0, (z[0] - z[-1]) / d[-1] * 100.0)

    return loss, max_grade


def loss_feet(loss_m: float) -> float:
    """Metres of descent in feet (US roads / longboarding are quoted in feet)."""
    return loss_m * _FEET_PER_M
