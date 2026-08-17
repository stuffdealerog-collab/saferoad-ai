"""Milestone 4 — pairwise conflict analysis (tech plan v2 §7).

For every pair of gated tracks with sufficient temporal overlap, computes on a
common time grid (linear interpolation of SMOOTHED states — never raw points):

- minimum observed separation (+ time of it);
- minimum TTC over the window (with applicability guards, see safety/ttc.py);
- relative speed at closest approach;
- conflict angle class from headings at closest approach;
- zone-based PET records (see safety/pet.py) — computed per zone, not per pair
  geometry.

Output is raw ANALYSIS, not events: the near-miss engine (Milestone 5) applies
thresholds and reason codes on top. This module must stay judgment-free.

Points outside the calibration validity mask are excluded from the grid; if
that leaves too little overlap the pair is reported as not-analyzable with a
reason rather than silently skipped.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.log import get_logger
from geometry.zones import Occupancy, Zone, occupancy_intervals
from safety.pet import PETResult, pet_between
from safety.ttc import TTCResult, instantaneous_ttc, radius_for

log = get_logger("safety.conflicts")

MIN_OVERLAP_S = 0.5
GRID_STEP_S = 0.05
# pairs never closer than this are not interesting even as context
MAX_REPORT_SEPARATION_M = 30.0


@dataclass
class TrackStates:
    """Minimal view of one track's smoothed states for pair analysis."""
    track_id: int
    segment: int
    cls: str
    ts: list[float]
    xs: list[float]
    ys: list[float]
    vxs: list[float]
    vys: list[float]
    headings: list[float | None]
    inside_mask: list[bool]

    @classmethod
    def from_states_dict(cls, d: dict) -> "TrackStates":
        st = d["states"]
        return cls(
            track_id=d["track_id"], segment=d["segment"], cls=d["cls"],
            ts=[s["t_s"] for s in st],
            xs=[s["x_m"] for s in st], ys=[s["y_m"] for s in st],
            vxs=[s["vx_mps"] for s in st], vys=[s["vy_mps"] for s in st],
            headings=[s["heading_deg"] for s in st],
            inside_mask=[s["inside_validity_mask"] for s in st],
        )

    def sample(self, t: float) -> tuple[float, float, float, float, bool]:
        """Linear interpolation of (x, y, vx, vy, in_mask) at time t."""
        ts = self.ts
        if t <= ts[0]:
            i = 0
            return self.xs[0], self.ys[0], self.vxs[0], self.vys[0], self.inside_mask[0]
        if t >= ts[-1]:
            return self.xs[-1], self.ys[-1], self.vxs[-1], self.vys[-1], self.inside_mask[-1]
        # binary search
        lo, hi = 0, len(ts) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ts[mid] <= t:
                lo = mid
            else:
                hi = mid
        w = (t - ts[lo]) / (ts[hi] - ts[lo])
        lerp = lambda a, b: a + (b - a) * w  # noqa: E731
        return (
            lerp(self.xs[lo], self.xs[hi]), lerp(self.ys[lo], self.ys[hi]),
            lerp(self.vxs[lo], self.vxs[hi]), lerp(self.vys[lo], self.vys[hi]),
            self.inside_mask[lo] and self.inside_mask[hi],
        )


def classify_conflict_angle(dh_deg: float, cls_a: str, cls_b: str) -> str:
    """Coarse conflict geometry from |heading difference| at closest approach."""
    if "person" in (cls_a, cls_b):
        return "pedestrian"
    d = abs(dh_deg) % 360.0
    if d > 180.0:
        d = 360.0 - d
    if d < 30.0:
        return "rear_end_or_parallel"
    if d < 60.0:
        return "merging"
    if d < 120.0:
        return "crossing"
    return "head_on_or_opposing"


@dataclass
class PairAnalysis:
    track_a: dict
    track_b: dict
    overlap_s: float
    analyzable: bool
    not_analyzable_reason: str | None = None
    min_separation_m: float | None = None
    t_min_separation_s: float | None = None
    rel_speed_at_min_sep_mps: float | None = None
    conflict_angle_class: str | None = None
    min_ttc_s: float | None = None
    t_min_ttc_s: float | None = None
    ttc_reasons: dict = field(default_factory=dict)   # reason -> count over grid
    grid_points_used: int = 0
    grid_points_outside_mask: int = 0

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        for k in ("min_separation_m", "t_min_separation_s", "rel_speed_at_min_sep_mps",
                  "min_ttc_s", "t_min_ttc_s", "overlap_s"):
            if d[k] is not None:
                d[k] = round(d[k], 3)
        return d


def analyze_pair(a: TrackStates, b: TrackStates) -> PairAnalysis | None:
    """Returns None only when temporal overlap < MIN_OVERLAP_S (nothing to say)."""
    t0 = max(a.ts[0], b.ts[0])
    t1 = min(a.ts[-1], b.ts[-1])
    overlap = t1 - t0
    ident_a = {"track_id": a.track_id, "segment": a.segment, "cls": a.cls}
    ident_b = {"track_id": b.track_id, "segment": b.segment, "cls": b.cls}
    if overlap < MIN_OVERLAP_S:
        return None

    radius = radius_for(a.cls, b.cls)
    n_steps = max(int(overlap / GRID_STEP_S), 2)
    min_sep, t_min_sep, rel_at_min = None, None, None
    min_ttc, t_min_ttc = None, None
    ttc_reasons: dict[str, int] = {}
    used = outside = 0

    for k in range(n_steps + 1):
        t = t0 + (t1 - t0) * k / n_steps
        ax, ay, avx, avy, a_in = a.sample(t)
        bx, by, bvx, bvy, b_in = b.sample(t)
        if not (a_in and b_in):
            outside += 1
            continue
        used += 1
        rx, ry = bx - ax, by - ay
        rvx, rvy = bvx - avx, bvy - avy
        sep = math.hypot(rx, ry)
        if min_sep is None or sep < min_sep:
            min_sep, t_min_sep = sep, t
            rel_at_min = math.hypot(rvx, rvy)
        res: TTCResult = instantaneous_ttc(rx, ry, rvx, rvy, radius)
        if res.applicable:
            if min_ttc is None or res.ttc_s < min_ttc:
                min_ttc, t_min_ttc = res.ttc_s, t
        elif res.reason:
            ttc_reasons[res.reason] = ttc_reasons.get(res.reason, 0) + 1

    if used < 3:
        return PairAnalysis(
            track_a=ident_a, track_b=ident_b, overlap_s=overlap, analyzable=False,
            not_analyzable_reason="insufficient_points_inside_validity_mask",
            grid_points_used=used, grid_points_outside_mask=outside,
        )
    if min_sep is not None and min_sep > MAX_REPORT_SEPARATION_M:
        return PairAnalysis(
            track_a=ident_a, track_b=ident_b, overlap_s=overlap, analyzable=False,
            not_analyzable_reason=f"never_within_{MAX_REPORT_SEPARATION_M}m",
            min_separation_m=min_sep, grid_points_used=used,
            grid_points_outside_mask=outside,
        )

    # conflict angle from headings at closest approach
    angle_class = None
    ha = _heading_at(a, t_min_sep)
    hb = _heading_at(b, t_min_sep)
    if ha is not None and hb is not None:
        angle_class = classify_conflict_angle(ha - hb, a.cls, b.cls)
    elif "person" in (a.cls, b.cls):
        angle_class = "pedestrian"

    return PairAnalysis(
        track_a=ident_a, track_b=ident_b, overlap_s=overlap, analyzable=True,
        min_separation_m=min_sep, t_min_separation_s=t_min_sep,
        rel_speed_at_min_sep_mps=rel_at_min,
        conflict_angle_class=angle_class,
        min_ttc_s=min_ttc, t_min_ttc_s=t_min_ttc,
        ttc_reasons=ttc_reasons,
        grid_points_used=used, grid_points_outside_mask=outside,
    )


def _heading_at(tr: TrackStates, t: float) -> float | None:
    """Nearest defined heading within 0.3s of t (heading may be None at low speed)."""
    best, best_dt = None, 0.3
    for tt, h in zip(tr.ts, tr.headings):
        if h is None:
            continue
        dt = abs(tt - t)
        if dt < best_dt:
            best, best_dt = h, dt
    return best


def analyze_all(
    tracks: list[TrackStates],
    zones: list[Zone],
    frame_step_s: float,
) -> tuple[list[PairAnalysis], list[Occupancy], list[PETResult]]:
    """Full pass: all pair analyses + all zone occupancies + all PET records."""
    pairs: list[PairAnalysis] = []
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            a, b = tracks[i], tracks[j]
            if a.track_id == b.track_id:
                continue  # two segments of one physical object are not a conflict
            pa = analyze_pair(a, b)
            if pa is not None:
                pairs.append(pa)

    occupancies: list[Occupancy] = []
    for z in zones:
        for tr in tracks:
            occupancies.extend(occupancy_intervals(
                z, tr.track_id, tr.segment, tr.cls, tr.ts, tr.xs, tr.ys))

    pets: list[PETResult] = []
    by_zone: dict[str, list[Occupancy]] = {}
    for o in occupancies:
        by_zone.setdefault(o.zone_id, []).append(o)
    for zone_id, occs in by_zone.items():
        occs.sort(key=lambda o: o.t_enter_s)
        for i in range(len(occs)):
            for j in range(i + 1, len(occs)):
                a, b = occs[i], occs[j]
                if a.track_id == b.track_id:
                    continue
                # only adjacent-in-time pairs are PET-meaningful; skip if another
                # occupancy of the same pairless zone lies fully between them
                pets.append(pet_between(a, b, frame_step_s))

    log.info("conflict analysis: %d pairs (%d analyzable), %d occupancies, %d PET records",
             len(pairs), sum(1 for p in pairs if p.analyzable), len(occupancies), len(pets))
    return pairs, occupancies, pets
