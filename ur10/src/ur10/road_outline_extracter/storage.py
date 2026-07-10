"""On-disk format for saved runs.

Each run lives in its own folder under a roads directory:

    roads/<slug>/
        centerline.geojson   canonical geometry (WGS84) + summary properties
        meta.json            RoadMetadata
        plot.json            last-used PlotConfig (optional)
        plot.svg             exported SVG (written by the plotting stage)

WGS84 is the single source of truth for geometry; the projected (UTM) line is
reconstructed on load from the stored EPSG. Everything is plain JSON so the
folder is git-friendly and hand-inspectable.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from shapely.geometry import LineString

from . import geometry
from .models import ExtractedRoad, LabelConfig, LatLon, PlotConfig, RoadMetadata, RoadRun

DEFAULT_ROADS_DIR = Path("roads")

_CENTERLINE = "centerline.geojson"
_META = "meta.json"
_PLOT = "plot.json"
_LABEL = "label.json"


def road_dir(slug: str, base_dir: Path = DEFAULT_ROADS_DIR) -> Path:
    """Folder for a given run's slug."""
    return Path(base_dir) / slug


def slugify(text: str) -> str:
    """Filesystem-safe slug: lowercase, alphanumerics joined by hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "road"


def slug_for(metadata: RoadMetadata) -> str:
    """Pick a slug from a run's name, preferring the nickname."""
    return slugify(metadata.nickname or metadata.real_name or "road")


def _geojson_feature(run: RoadRun) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "slug": run.slug,
            "length_m": run.road.length_m,
            "n_points": run.road.n_points,
            "utm_epsg": run.road.utm_epsg,
        },
        "geometry": {
            "type": "LineString",
            "coordinates": [[x, y] for x, y in run.road.line_wgs84.coords],
        },
    }


def _metadata_to_dict(metadata: RoadMetadata) -> dict:
    data = asdict(metadata)  # nested LatLon dataclasses become dicts
    if not data.get("created_at"):
        data["created_at"] = datetime.now().isoformat(timespec="seconds")
    return data


def _metadata_from_dict(data: dict) -> RoadMetadata:
    def latlon(value: dict | None) -> LatLon | None:
        return LatLon(**value) if value else None

    return RoadMetadata(
        nickname=data.get("nickname"),
        real_name=data.get("real_name"),
        date_first_skated=data.get("date_first_skated"),
        start=latlon(data.get("start")),
        finish=latlon(data.get("finish")),
        created_at=data.get("created_at"),
    )


def save_road(run: RoadRun, base_dir: Path = DEFAULT_ROADS_DIR) -> Path:
    """Write a run's geometry, metadata, and plot config. Returns its folder."""
    folder = Path(base_dir) / run.slug
    folder.mkdir(parents=True, exist_ok=True)

    (folder / _CENTERLINE).write_text(json.dumps(_geojson_feature(run), indent=2))
    (folder / _META).write_text(json.dumps(_metadata_to_dict(run.metadata), indent=2))
    if run.plot_config is not None:
        (folder / _PLOT).write_text(json.dumps(asdict(run.plot_config), indent=2))
    if run.label_config is not None:
        (folder / _LABEL).write_text(json.dumps(asdict(run.label_config), indent=2))

    return folder


def load_road(slug: str, base_dir: Path = DEFAULT_ROADS_DIR) -> RoadRun:
    """Reconstruct a RoadRun from disk, reprojecting geometry to its saved zone."""
    folder = Path(base_dir) / slug

    feature = json.loads((folder / _CENTERLINE).read_text())
    props = feature["properties"]
    line_wgs84 = LineString(feature["geometry"]["coordinates"])
    utm_epsg = int(props["utm_epsg"])
    line_utm = geometry.project_line_to_epsg(line_wgs84, utm_epsg)
    road = ExtractedRoad(
        line_wgs84=line_wgs84,
        line_utm=line_utm,
        utm_epsg=utm_epsg,
        length_m=float(props["length_m"]),
    )

    meta_path = folder / _META
    if meta_path.exists():
        metadata = _metadata_from_dict(json.loads(meta_path.read_text()))
    else:
        # A geometry-only folder (e.g. produced by an extraction spike) is still
        # plottable; it just has no user metadata yet.
        metadata = RoadMetadata()

    plot_config = None
    plot_path = folder / _PLOT
    if plot_path.exists():
        plot_config = PlotConfig(**json.loads(plot_path.read_text()))

    label_config = None
    label_path = folder / _LABEL
    if label_path.exists():
        label_config = LabelConfig(**json.loads(label_path.read_text()))

    return RoadRun(
        slug=slug,
        road=road,
        metadata=metadata,
        plot_config=plot_config,
        label_config=label_config,
    )


def list_roads(base_dir: Path = DEFAULT_ROADS_DIR) -> list[str]:
    """Slugs of all saved runs (folders containing a centerline), sorted."""
    base = Path(base_dir)
    if not base.exists():
        return []
    return sorted(
        p.name for p in base.iterdir() if p.is_dir() and (p / _CENTERLINE).exists()
    )
