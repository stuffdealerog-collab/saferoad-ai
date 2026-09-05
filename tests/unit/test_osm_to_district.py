"""Unit tests for the OSM -> district converter.

Constructed Overpass responses with known answers, so the converter is trusted
before it ever meets a real 5 MB export of Tashkent.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.osm_to_district import build, project  # noqa: E402

LAT, LON = 41.29, 69.28


def node(lat, lon):
    return {"lat": lat, "lon": lon}


def way(wid, name, cls, node_ids, coords, **tags):
    t = {"highway": cls}
    if name:
        t["name"] = name
    t.update(tags)
    return {"type": "way", "id": wid, "tags": t,
            "nodes": node_ids, "geometry": [node(a, b) for a, b in coords]}


def crossing_pair():
    """Two named streets crossing at a shared node 100 -> exactly one junction."""
    return {"elements": [
        way(1, "Шота Руставели", "secondary", [10, 100, 11],
            [(LAT, LON - 0.004), (LAT, LON), (LAT, LON + 0.004)], lanes="4", maxspeed="60"),
        way(2, "Нукус", "tertiary", [20, 100, 21],
            [(LAT - 0.003, LON), (LAT, LON), (LAT + 0.003, LON)]),
    ]}


def test_projection_is_metric_and_centred():
    x, y = project(LAT, LON, LAT, LON)
    assert abs(x) < 1e-6 and abs(y) < 1e-6
    # one thousandth of a degree of latitude is ~111 m
    _, y2 = project(LAT + 0.001, LON, LAT, LON)
    assert 105 < y2 < 115


def test_two_named_streets_make_one_junction():
    out = build(crossing_pair(), "Тест")
    assert len(out["roads"]) == 2
    assert len(out["junctions"]) == 1
    j = out["junctions"][0]
    assert j["arms"] == 4              # both ways pass through: two arms each
    assert "Шота Руставели" in j["label"] and "Нукус" in j["label"]
    assert j["cls"] == "secondary"      # the more important of the two
    assert j["maxspeed"] == 60


def test_street_crossing_itself_is_not_a_junction():
    """A loop or a self-touching way is a geometry artefact, not an intersection."""
    data = {"elements": [
        way(1, "Кольцевая", "residential", [10, 100, 11],
            [(LAT, LON - 0.002), (LAT, LON), (LAT, LON + 0.002)]),
        way(2, "Кольцевая", "residential", [20, 100, 21],
            [(LAT - 0.002, LON), (LAT, LON), (LAT + 0.002, LON)]),
    ]}
    assert build(data, "Тест")["junctions"] == []


def test_unnamed_service_crossing_is_dropped():
    data = {"elements": [
        way(1, "Шота Руставели", "secondary", [10, 100, 11],
            [(LAT, LON - 0.002), (LAT, LON), (LAT, LON + 0.002)]),
        way(2, "", "residential", [20, 100, 21],
            [(LAT - 0.002, LON), (LAT, LON), (LAT + 0.002, LON)]),
    ]}
    assert build(data, "Тест")["junctions"] == []


def test_nearby_nodes_merge_into_one_intersection():
    """A dual carriageway splits one real junction into two nodes ~20 m apart."""
    data = {"elements": [
        way(1, "Афросиаб", "primary", [10, 100, 11],
            [(LAT, LON - 0.004), (LAT, LON), (LAT, LON + 0.004)]),
        way(2, "Ойбека", "secondary", [20, 100, 21],
            [(LAT - 0.003, LON), (LAT, LON), (LAT + 0.003, LON)]),
        # second node of the same junction, ~22 m north
        way(3, "Афросиаб", "primary", [30, 101, 31],
            [(LAT + 0.0002, LON - 0.004), (LAT + 0.0002, LON), (LAT + 0.0002, LON + 0.004)]),
        way(4, "Ойбека", "secondary", [40, 101, 41],
            [(LAT - 0.003, LON), (LAT + 0.0002, LON), (LAT + 0.003, LON)]),
    ]}
    out = build(data, "Тест")
    assert len(out["junctions"]) == 1, "два узла одного перекрёстка должны схлопнуться"


def test_link_roads_never_anchor_a_junction():
    """A slip lane joining a road is not an intersection of two streets."""
    data = {"elements": [
        way(1, "Магистраль", "primary", [10, 100, 11],
            [(LAT, LON - 0.003), (LAT, LON), (LAT, LON + 0.003)]),
        way(2, "Съезд", "primary_link", [20, 100, 21],
            [(LAT - 0.001, LON), (LAT, LON), (LAT + 0.001, LON)]),
    ]}
    assert build(data, "Тест")["junctions"] == []


def test_traffic_signal_node_marks_the_junction():
    data = crossing_pair()
    data["elements"].append(
        {"type": "node", "id": 100, "lat": LAT, "lon": LON,
         "tags": {"highway": "traffic_signals"}})
    assert build(data, "Тест")["junctions"][0]["signal"] is True


def test_empty_or_wrong_input_fails_loudly():
    """Silence on bad input is how a demo dies on stage; fail with a reason."""
    with pytest.raises(SystemExit):
        build({"elements": []}, "Тест")
    with pytest.raises(SystemExit):
        build({"nope": 1}, "Тест")


def test_output_carries_attribution_and_bbox():
    out = build(crossing_pair(), "Мирабадский район, Ташкент")
    assert "OpenStreetMap" in out["source"] and "ODbL" in out["source"]
    assert out["name"] == "Мирабадский район, Ташкент"
    x0, y0, x1, y1 = out["bbox_m"]
    assert x1 > x0 and y1 > y0
    assert math.isclose(out["origin"]["lat"], LAT, abs_tol=1e-3)
