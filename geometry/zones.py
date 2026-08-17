"""Milestone 4 — conflict zones (tech plan v2 §5, fix #2 of the audit).

PET is only defined relative to a spatial conflict zone that two road users
successively occupy. Without zone definitions PET is NOT computable — the v1
plan listed PET but never defined zones; this module closes that gap.

Zones are ground-plane polygons in the per-camera YAML (``geometry.conflict_zones``).

Critical correctness guard: if a track ENDS while inside a zone (occlusion,
frame edge, gap split), its exit time is unknown — an occupancy interval
truncated that way must never be used as a PET exit event. We flag it
(``exit_observed=False``) and PET computations refuse it with a reason code
instead of silently producing a fake small PET.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from core.log import get_logger

log = get_logger("geometry.zones")


@dataclass
class Zone:
    zone_id: str
    zone_type: str                    # pedestrian_crossing | junction | approach | other
    polygon_m: np.ndarray             # (N,2) ground coords, meters

    def contains(self, x_m: float, y_m: float) -> bool:
        # ray casting; polygon is small (<20 vertices), plain python is fine
        poly = self.polygon_m
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if (yi > y_m) != (yj > y_m):
                x_cross = (xj - xi) * (y_m - yi) / (yj - yi) + xi
                if x_m < x_cross:
                    inside = not inside
            j = i
        return inside


@dataclass
class Occupancy:
    """One continuous stay of one track inside one zone."""
    zone_id: str
    track_id: int
    segment: int
    cls: str
    t_enter_s: float
    t_exit_s: float
    enter_observed: bool = True   # False: track already inside at its first point
    exit_observed: bool = True    # False: track ended while still inside (occlusion!)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id, "track_id": self.track_id, "segment": self.segment,
            "cls": self.cls,
            "t_enter_s": round(self.t_enter_s, 3), "t_exit_s": round(self.t_exit_s, 3),
            "enter_observed": self.enter_observed, "exit_observed": self.exit_observed,
        }


def load_zones(camera_yaml: str | Path) -> list[Zone]:
    cfg = yaml.safe_load(Path(camera_yaml).read_text())
    zones = []
    for z in (cfg.get("geometry", {}) or {}).get("conflict_zones", []) or []:
        zones.append(Zone(
            zone_id=z["id"],
            zone_type=z.get("type", "other"),
            polygon_m=np.asarray(z["polygon_ground_m"], dtype=float),
        ))
    if not zones:
        log.warning("camera %s: no conflict zones defined — PET will not be computable",
                    cfg.get("camera_id"))
    return zones


def occupancy_intervals(
    zone: Zone,
    track_id: int,
    segment: int,
    cls: str,
    ts: list[float],
    xs_m: list[float],
    ys_m: list[float],
) -> list[Occupancy]:
    """Continuous in-zone intervals of one track. Sampling is the track's own
    timestep, so enter/exit precision is bounded by the actual frame interval
    (tech plan v2 §7: PET is published at frame-step resolution, finer
    differences are not interpretable)."""
    out: list[Occupancy] = []
    inside_prev = False
    t_enter = 0.0
    enter_observed = True
    for i, (t, x, y) in enumerate(zip(ts, xs_m, ys_m)):
        inside = zone.contains(x, y)
        if inside and not inside_prev:
            t_enter = t
            enter_observed = i > 0
        if not inside and inside_prev:
            out.append(Occupancy(zone.zone_id, track_id, segment, cls,
                                 t_enter, ts[i - 1], enter_observed, True))
        inside_prev = inside
    if inside_prev:
        # track ended inside the zone -> exit NOT observed
        out.append(Occupancy(zone.zone_id, track_id, segment, cls,
                             t_enter, ts[-1], enter_observed, False))
    return out
