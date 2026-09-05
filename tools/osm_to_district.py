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

# Geometry simplification: at map scale a 1.5 m deviation is invisible, and the
# file has to load on a phone over a conference wifi.
SIMPLIFY_EPS_M = 1.5

# What counts as a junction worth monitoring. A yard passage crossing another
# yard passage is not a place you put a camera, however many arms it has.
MONITOR_MAX_RANK = CLASS_RANK["tertiary"]     # the major road must be this or better
MONITOR_MINOR_EXCLUDE = {"living_street"}     # the minor road may not be a yard passage
MONITOR_SPACING_M = 220.0                     # keep the set spread over the district
MONITOR_LIMIT = 48
# Quotas per class band. Ranking alone hands every camera to the arterials, and a
# district's hazard list that contains no residential street is not a district's
# hazard list — school approaches and side roads are where pedestrians get hit.
MONITOR_QUOTA = [
    (("motorway", "trunk", "primary"), 14),
    (("secondary",), 12),
    (("tertiary",), 12),
    (("unclassified", "residential"), 10),
]


def simplify(pts: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    """Douglas-Peucker. Iterative, because a district has ways with 400+ nodes and
    the recursive form blows the stack on the worst of them."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]
        bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        den = math.hypot(dx, dy)
        worst, worst_k = -1.0, -1
        for k in range(i + 1, j):
            px, py = pts[k]
            d = (abs(dy * px - dx * py + bx * ay - by * ax) / den) if den > 1e-9 \
                else math.dist((px, py), (ax, ay))
            if d > worst:
                worst, worst_k = d, k
        if worst > eps:
            keep[worst_k] = True
            stack.append((i, worst_k))
            stack.append((worst_k, j))
    return [p for p, k in zip(pts, keep) if k]


def pick_monitored(junctions: list[dict]) -> list[dict]:
    """Rank the junctions and thin them out spatially.

    Ranking alone clusters every pick onto one arterial; a road authority needs
    the district covered, not one street sampled forty times.
    """
    picked: list[dict] = []
    for classes, quota in MONITOR_QUOTA:
        band = [j for j in junctions
                if j["cls"] in classes
                and j.get("minor_cls") not in MONITOR_MINOR_EXCLUDE]
        band.sort(key=lambda j: (j["rank"], -j["arms"]))
        taken = 0
        for j in band:
            if taken >= quota or len(picked) >= MONITOR_LIMIT:
                break
            if any(math.dist((j["x"], j["y"]), (p["x"], p["y"])) < MONITOR_SPACING_M
                   for p in picked):
                continue
            picked.append(j)
            taken += 1
    return picked


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
            "pts": [[round(x, 1), round(y, 1)] for x, y in simplify(pts, SIMPLIFY_EPS_M)],
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
        ranks = sorted(CLASS_RANK[r["cls"]] for r in anchors)
        rank, minor_rank = ranks[0], ranks[-1]
        minor_cls = next(c for c, v in CLASS_RANK.items() if v == minor_rank)
        x, y = node_pos[nid]
        raw_junctions.append({
            "id": nid, "x": round(x, 1), "y": round(y, 1),
            "cls": min(anchors, key=lambda r: CLASS_RANK[r["cls"]])["cls"],
            "rank": rank, "arms": arms, "minor_cls": minor_cls,
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
    monitored = pick_monitored(junctions)
    for j in junctions:
        j["label"] = " × ".join(j["names"]) if len(j["names"]) > 1 else (j["names"][0] if j["names"] else "—")
        j.pop("names", None)

    xs = [p[0] for r in roads for p in r["pts"]]
    ys = [p[1] for r in roads for p in r["pts"]]

    # Compact form: the page carries this inline so it opens from file:// with no
    # server, so every byte is one the demo laptop has to parse. Street names are
    # already baked into the junction labels, so the drawn roads need only a class
    # and a flat coordinate list.
    classes = sorted(CLASS_RANK, key=lambda c: CLASS_RANK[c])
    cls_idx = {c: i for i, c in enumerate(classes)}
    flat_roads = [
        [cls_idx[r["cls"]]] + [v for p in r["pts"] for v in p]
        for r in roads if len(r["pts"]) >= 2
    ]
    for j in monitored:
        j.pop("minor_cls", None)
        j.pop("rank", None)

    return {
        "name": district_name,
        "source": "OpenStreetMap contributors, ODbL",
        "origin": {"lat": round(lat0, 6), "lon": round(lon0, 6)},
        "bbox_m": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
        "road_classes": classes,
        "roads": flat_roads,
        "junctions": monitored,
        "junctions_found": len(junctions),
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
    pts = sum((len(r) - 1) // 2 for r in out["roads"])
    print(f"дорог:      {len(out['roads'])}, точек {pts}")
    print(f"перекрёстков: найдено {out['junctions_found']}, "
          f"под наблюдение отобрано {len(out['junctions'])}")
    print(f"охват:      {w/1000:.1f} × {h/1000:.1f} км")
    print(f"записано:   {dst} ({dst.stat().st_size/1024:.0f} КБ)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
