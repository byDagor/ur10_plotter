"""Round-trip tests for the storage layer (no network required)."""

from __future__ import annotations

from shapely.geometry import LineString

from road_outline_extracter import geometry, storage
from road_outline_extracter.models import (
    ExtractedRoad,
    LatLon,
    PlotConfig,
    RoadMetadata,
    RoadRun,
)


def _make_road() -> ExtractedRoad:
    line_wgs84 = LineString(
        [(-121.6429, 37.3415), (-121.6440, 37.3420), (-121.6450, 37.3410)]
    )
    line_utm, epsg = geometry.project_line_to_utm(line_wgs84)
    return ExtractedRoad(
        line_wgs84=line_wgs84, line_utm=line_utm, utm_epsg=epsg, length_m=line_utm.length
    )


def test_slugify():
    assert storage.slugify("Mount Hamilton!") == "mount-hamilton"
    assert storage.slugify("  El Toyonal / Lower  ") == "el-toyonal-lower"
    assert storage.slugify("") == "road"


def test_slug_for_prefers_nickname():
    meta = RoadMetadata(nickname="The Lick Drop", real_name="Mount Hamilton Road")
    assert storage.slug_for(meta) == "the-lick-drop"
    assert storage.slug_for(RoadMetadata(real_name="Mount Hamilton Road")) == "mount-hamilton-road"


def test_save_load_roundtrip(tmp_path):
    road = _make_road()
    meta = RoadMetadata(
        nickname="The Lick Drop",
        real_name="Mount Hamilton Road",
        date_first_skated="2021-06-01",
        start=LatLon(37.3415, -121.6429),
        finish=LatLon(37.3410, -121.6450),
    )
    config = PlotConfig(canvas_w_mm=594, canvas_h_mm=841, stroke_count=3, stroke_offset_mm=0.65)
    run = RoadRun(slug="mount-hamilton-road", road=road, metadata=meta, plot_config=config)

    storage.save_road(run, base_dir=tmp_path)
    assert storage.list_roads(tmp_path) == ["mount-hamilton-road"]

    loaded = storage.load_road("mount-hamilton-road", base_dir=tmp_path)

    assert loaded.slug == "mount-hamilton-road"
    assert loaded.metadata.nickname == "The Lick Drop"
    assert loaded.metadata.real_name == "Mount Hamilton Road"
    assert loaded.metadata.date_first_skated == "2021-06-01"
    assert loaded.metadata.start == LatLon(37.3415, -121.6429)
    assert loaded.metadata.finish == LatLon(37.3410, -121.6450)
    assert loaded.metadata.created_at is not None  # stamped on save

    assert loaded.plot_config.canvas_w_mm == 594
    assert loaded.plot_config.stroke_count == 3
    assert loaded.plot_config.stroke_offset_mm == 0.65

    assert loaded.road.utm_epsg == road.utm_epsg
    assert loaded.road.length_m == road.length_m

    original = list(road.line_wgs84.coords)
    restored = list(loaded.road.line_wgs84.coords)
    assert len(original) == len(restored)
    for (ox, oy), (rx, ry) in zip(original, restored):
        assert abs(ox - rx) < 1e-9
        assert abs(oy - ry) < 1e-9


def test_created_at_preserved_on_resave(tmp_path):
    road = _make_road()
    meta = RoadMetadata(nickname="test", created_at="2020-01-01T00:00:00")
    run = RoadRun(slug="test", road=road, metadata=meta)

    storage.save_road(run, base_dir=tmp_path)
    loaded = storage.load_road("test", base_dir=tmp_path)
    assert loaded.metadata.created_at == "2020-01-01T00:00:00"


def test_list_roads_empty(tmp_path):
    assert storage.list_roads(tmp_path / "does-not-exist") == []
