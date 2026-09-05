"""Convert an Overpass road-network export into the district file the simulation reads.

Input  : Overpass JSON produced by `out body geom;` (see tools/mirabad_query.overpassql)
Output : landing/data/district.json — roads as local-metric polylines plus the
         junctions worth monitoring, ranked so the demo shows real streets.

Why local metres and not lat/lon: the whole safety engine works in the ground
plane in metres (tech plan v2, invariant "пиксели и метры не смешиваются"). The
map must speak the same units, otherwise every distance on screen is a lie.

Source data is OpenStreetMap, ODbL. Attribution is carried into the output and
must stay visible in the UI.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# Road classes we keep, ordered by importance. The order drives junction ranking:
# a crossing of two arterials matters more than two side streets.
CLASS_RANK = {
    "motorway": 0, "trunk": 1, "primary": 2, "secondary": 3,
    "tertiary": 4, "unclassified": 5, "residential": 6, "living_street": 7,
}
# Link roads (slip lanes) inherit their parent class but never anchor a junction.
LINK_SUFFIX = "_link"

# Two junction nodes closer than this are the same real intersection split by
# OSM into several nodes (dual carriageways, turn lanes). Merge them.
MERGE_RADIUS_M = 35.0

# A junction needs at least this many road arms to be worth a camera.
MIN_ARMS = 3


def base_class(hw: str) -> str:
    return hw[: -len(LINK_SUFFIX)] if hw.endswith(LINK_SUFFIX) else hw


def project(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Equirectangular projection about the origin. Over a district-sized area the
    distortion is well under a metre, which is far below anything we claim."""
    x = math.radians(lon - lon0) * 6378137.0 * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * 6356752.0
    return x, y


def parse_speed(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(str(v).split()[0])
    except (ValueError, IndexError):
        return None


def parse_lanes(v: str | None) -> int | None:
    try:
        return max(1, int(str(v).split(";")[0])) if v else None
    except (ValueError, IndexError):
        return None


def load_elements(raw: dict) -> list[dict]:
    els = raw.get("elements")
    if not isinstance(els, list):
        raise SystemExit("не похоже на ответ Overpass: нет списка elements")
    return els


def build(raw: dict, district_name: str) -> dict:
    elements = load_elements(raw)
    ways = [
        e for e in elements
        if e.get("type") == "way"
        and e.get("geometry")
        and e.get("nodes")
        and base_class(e.get("tags", {}).get("highway", "")) in CLASS_RANK
    ]
    if not ways:
        raise SystemExit(
            "в файле нет ни одной дороги нужного класса — проверьте, что "
            "экспортировали raw OSM data (JSON), а не GeoJSON, и что рамка "
            "запроса накрывает район"
        )

    lats = [p["lat"] for w in ways for p in w["geometry"]]
    lons = [p["lon"] for w in ways for p in w["geometry"]]
    lat0, lon0 = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2

    roads: list[dict] = []
    # node id -> list of (road index, is_endpoint). Endpoint vs interior matters:
    # a way passing THROUGH a node contributes two arms, one ending there only one.
    node_ways: dict[int, list[tuple[int, bool]]] = {}
    node_pos: dict[int, tuple[float, float]] = {}

    for w in ways:
        tags = w.get("tags", {})
        hw = tags["highway"]
        pts = [project(p["lat"], p["lon"], lat0, lon0) for p in w["geometry"]]
        idx = len(roads)
        roads.append({
            "id": w["id"],
            "name": tags.get("name") or tags.get("name:ru") or tags.get("name:uz") or "",
            "cls": base_class(hw),
            "link": hw.endswith(LINK_SUFFIX),
            "lanes": parse_lanes(tags.get("lanes")),
            "maxspeed": parse_speed(tags.get("maxspeed")),
            "oneway": tags.get("oneway") in ("yes", "1", "-1"),
            "pts": [[round(x, 1), round(y, 1)] for x, y in pts],
        })
        last = len(w["nodes"]) - 1
        for pos, (nid, (x, y)) in enumerate(zip(w["nodes"], pts)):
            node_ways.setdefault(nid, []).append((idx, pos == 0 or pos == last))
            node_pos[nid] = (x, y)

    # Signalised nodes, when the export happens to include them.
    signals = {
        e["id"] for e in elements
        if e.get("type") == "node" and e.get("tags", {}).get("highway") == "traffic_signals"
    }

    raw_junctions = []
    for nid, uses in node_ways.items():
        if len(uses) < 2:
            continue
        arms = sum(1 if endpoint else 2 for _, endpoint in uses)
        members = [roads[i] for i in dict.fromkeys(i for i, _ in uses)]
        anchors = [r for r in members if not r["link"]]
        if len(anchors) < 2:
            continue
        names = [r["name"] for r in anchors if r["name"]]
        # An intersection of a street with itself is a geometry artefact, not a junction.
        if len(set(names)) < 2:
            continue
        rank = min(CLASS_RANK[r["cls"]] for r in anchors)
        x, y = node_pos[nid]
        raw_junctions.append({
            "id": nid, "x": round(x, 1), "y": round(y, 1),
            "cls": min(anchors, key=lambda r: CLASS_RANK[r["cls"]])["cls"],
            "rank": rank, "arms": arms,
            "names": sorted(set(names))[:2],
            "signal": nid in signals,
            "maxspeed": max((r["maxspeed"] or 0) for r in anchors) or None,
        })

    # OSM splits one real intersection into several nodes. Merge by proximity,
    # keeping the most important member of each cluster.
    raw_junctions.sort(key=lambda j: (j["rank"], -j["arms"]))
    merged: list[dict] = []
    for j in raw_junctions:
        if any(math.dist((j["x"], j["y"]), (m["x"], m["y"])) < MERGE_RADIUS_M for m in merged):
            continue
        merged.append(j)

    junctions = [j for j in merged if j["arms"] >= MIN_ARMS]
    for j in junctions:
        j["label"] = " × ".join(j["names"]) if len(j["names"]) > 1 else (j["names"][0] if j["names"] else "—")
        j.pop("names", None)

    xs = [p[0] for r in roads for p in r["pts"]]
    ys = [p[1] for r in roads for p in r["pts"]]
    return {
        "name": district_name,
        "source": "OpenStreetMap contributors, ODbL",
        "origin": {"lat": round(lat0, 6), "lon": round(lon0, 6)},
        "bbox_m": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
        "roads": roads,
        "junctions": junctions,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        print("Использование: python tools/osm_to_district.py <overpass.json> "
              "[выход.json] [\"Название района\"]")
        return 2
    src = Path(argv[1])
    dst = Path(argv[2]) if len(argv) > 2 else Path("landing/data/district.json")
    name = argv[3] if len(argv) > 3 else "Мирабадский район, Ташкент"

    raw = json.loads(src.read_text(encoding="utf-8"))
    out = build(raw, name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    w = out["bbox_m"][2] - out["bbox_m"][0]
    h = out["bbox_m"][3] - out["bbox_m"][1]
    named = sum(1 for j in out["junctions"] if j["label"] != "—")
    print(f"дорог:      {len(out['roads'])}")
    print(f"перекрёстков: {len(out['junctions'])} (с названиями: {named})")
    print(f"охват:      {w/1000:.1f} × {h/1000:.1f} км")
    print(f"записано:   {dst} ({dst.stat().st_size/1024:.0f} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
