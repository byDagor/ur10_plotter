"""Tests for LatLon coordinate parsing (the paste-from-Google-Maps feature)."""

from __future__ import annotations

from road_outline_extracter.models import LatLon


def test_parse_comma_separated():
    assert LatLon.parse("37.3415, -121.6429") == LatLon(37.3415, -121.6429)


def test_parse_space_separated():
    assert LatLon.parse("37.3415 -121.6429") == LatLon(37.3415, -121.6429)


def test_parse_tolerates_extra_whitespace():
    assert LatLon.parse("  37.3415 ,  -121.6429  ") == LatLon(37.3415, -121.6429)


def test_parse_rejects_non_numeric():
    assert LatLon.parse("somewhere nice") is None


def test_parse_rejects_wrong_count():
    assert LatLon.parse("37.3415") is None
    assert LatLon.parse("37.3415, -121.6429, 5") is None


def test_parse_rejects_out_of_range():
    assert LatLon.parse("200, 0") is None
    assert LatLon.parse("0, 500") is None
