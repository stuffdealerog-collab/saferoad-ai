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


def test_simplify_keeps_shape_and_endpoints():
    from tools.osm_to_district import simplify
    straight = [(0, 0), (10, 0.2), (20, -0.1), (30, 0)]
    out = simplify(straight, 1.5)
    assert out[0] == (0, 0) and out[-1] == (30, 0)
    assert len(out) == 2, "почти прямая должна схлопнуться в две точки"

    corner = [(0, 0), (10, 0), (10, 10)]
    assert len(simplify(corner, 1.5)) == 3, "поворот терять нельзя"


def test_simplify_survives_a_long_way():
    """A 5000-node way must not blow the stack — real exports contain them."""
    from tools.osm_to_district import simplify
    pts = [(i * 1.0, math.sin(i / 40) * 12) for i in range(5000)]
    out = simplify(pts, 1.5)
    assert 2 < len(out) < len(pts)


def test_yard_passages_are_not_monitored():
    """A living_street crossing an arterial is a driveway, not a camera site."""
    from tools.osm_to_district import pick_monitored
    js = [
        {"x": 0, "y": 0, "rank": 2, "arms": 4, "cls": "primary", "minor_cls": "living_street"},
        {"x": 900, "y": 0, "rank": 3, "arms": 4, "cls": "secondary", "minor_cls": "secondary"},
    ]
    picked = pick_monitored(js)
    assert len(picked) == 1 and picked[0]["x"] == 900


def test_monitored_set_is_spread_not_clustered():
    """Ten junctions on one street 50 m apart must not eat the whole quota."""
    from tools.osm_to_district import pick_monitored, MONITOR_SPACING_M
    js = [{"x": i * 50.0, "y": 0.0, "rank": 2, "arms": 4,
           "cls": "primary", "minor_cls": "primary"} for i in range(10)]
    picked = pick_monitored(js)
    assert len(picked) < 10
    for a in range(len(picked)):
        for b in range(a + 1, len(picked)):
            d = math.dist((picked[a]["x"], picked[a]["y"]), (picked[b]["x"], picked[b]["y"]))
            assert d >= MONITOR_SPACING_M


def test_compact_output_is_flat_and_classed():
    """Roads ship as [class index, x, y, x, y, ...] — the page parses this inline."""
    out = build(crossing_pair(), "Тест")
    assert out["road_classes"][out["roads"][0][0]] in ("secondary", "tertiary")
    for r in out["roads"]:
        assert len(r) >= 5 and (len(r) - 1) % 2 == 0
    # street names live only in junction labels now, not on every road
    assert all(not isinstance(v, str) for r in out["roads"] for v in r)


def test_monitored_set_covers_more_than_arterials():
    """Ranking alone gives every camera to the big roads; quotas keep the mix."""
    from tools.osm_to_district import pick_monitored
    js = []
    for i in range(30):
        js.append({"x": i * 400.0, "y": 0.0, "rank": 2, "arms": 4,
                   "cls": "primary", "minor_cls": "primary"})
    for i in range(30):
        js.append({"x": i * 400.0, "y": 900.0, "rank": 6, "arms": 3,
                   "cls": "residential", "minor_cls": "residential"})
    picked = pick_monitored(js)
    kinds = {p["cls"] for p in picked}
    assert "primary" in kinds and "residential" in kinds, \
        "в перечне должны быть и магистрали, и жилые улицы"
