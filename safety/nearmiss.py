"""Milestone 5 — explainable near-miss classification (tech plan v2 §8).

Input: the judgment-free analysis artifacts of stage 06 (pair analyses, PET
records) plus braking episodes of stage 05. Output: ConflictEvents.

Design constraints (non-negotiable):
- a near-miss is NEVER "TTC < arbitrary threshold" alone: the score combines
  several signals, each contributing a transparent reason code;
- every threshold and weight lives in the versioned thresholds profile and is
  EXPERIMENTAL until validated against the golden set (Milestone 8);
- the risk score is a prioritization index, NEVER an accident probability;
- every event carries reason_codes + the raw metrics that fired them, so a
  reviewer can reconstruct WHY it exists (tech plan v2 §9: black-box output
  without evidence is unacceptable).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from core.log import get_logger

log = get_logger("safety.nearmiss")

DEFAULT_RULES = {
    # trigger thresholds (units in names) — experimental_v1
    "ttc_trigger_s": 2.0,
    "pet_trigger_s": 1.5,
    "separation_trigger_m": 2.0,
    "rel_speed_bonus_mps": 8.0,      # ~29 km/h relative speed adds weight
    "min_rel_speed_mps": 1.5,        # below this the pair is not a conflict, whatever
                                     # the geometry says (a walker easing past a parked
                                     # car yields TTC ~0 s at 0.1 m/s of closing speed)
    "hard_braking_window_s": 3.0,    # braking episode within this window of the conflict
    # reason-code weights
    "weights": {
        "low_ttc": 3.0,
        "very_low_ttc": 2.0,          # extra on top of low_ttc when < 1.0s
        "low_pet": 2.5,
        "very_low_pet": 2.0,          # extra when < 0.5s
        "simultaneous_occupancy": 3.5,
        "low_separation": 2.0,
        "high_rel_speed": 1.5,
        "pedestrian_involved": 2.0,
        "two_wheeler_involved": 1.5,
        "hard_braking_near_conflict": 1.5,
    },
    # severity bands over the summed score
    "severity_bands": {"critical": 7.0, "high": 5.0, "medium": 3.0, "low": 1.5},
}


@dataclass
class ConflictEvent:
    event_id: str
    t_start_s: float
    t_end_s: float
    road_user_a: dict          # {track_id, segment, cls}
    road_user_b: dict
    metrics: dict              # every metric with units in key names; None = n/a
    reason_codes: list[str]
    score: float
    severity: str              # critical | high | medium | low
    thresholds_profile_id: str
    zone_id: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _severity(score: float, bands: dict) -> str | None:
    for name in ("critical", "high", "medium", "low"):
        if score >= bands[name]:
            return name
    return None


def _pair_key(a: dict, b: dict) -> frozenset:
    return frozenset([(a["track_id"], a["segment"]), (b["track_id"], b["segment"])])


def build_events(
    pairs: list[dict],
    pets: list[dict],
    braking: list[dict],
    rules: dict | None = None,
    profile_id: str = "experimental_v1",
) -> list[ConflictEvent]:
    rules = {**DEFAULT_RULES, **(rules or {})}
    weights = rules["weights"]
    bands = rules["severity_bands"]

    # index PET records by pair of (track_id) for joining onto pair analyses
    pet_by_pair: dict[frozenset, list[dict]] = {}
    for p in pets:
        if p.get("first") is None or p.get("second") is None:
            continue
        key = frozenset([p["first"]["track_id"], p["second"]["track_id"]])
        pet_by_pair.setdefault(key, []).append(p)

    braking_by_track: dict[int, list[dict]] = {}
    for b in braking:
        braking_by_track.setdefault(b["track_id"], []).extend(b["episodes"])

    events: list[ConflictEvent] = []
    for pa in pairs:
        if not pa.get("analyzable"):
            continue
        a, b = pa["track_a"], pa["track_b"]
        # geometry alone is not enough: two bodies that barely move relative to each
        # other are not in conflict, however small the distance between them is.
        rel_at_sep = pa.get("rel_speed_at_min_sep_mps")
        if rel_at_sep is not None and rel_at_sep < rules["min_rel_speed_mps"]:
            continue
        codes: list[str] = []
        notes: list[str] = []
        score = 0.0
        times: list[float] = []

        # --- TTC ---
        ttc = pa.get("min_ttc_s")
        if ttc is not None and ttc < rules["ttc_trigger_s"]:
            codes.append("low_ttc")
            score += weights["low_ttc"]
            times.append(pa["t_min_ttc_s"])
            if ttc < 1.0:
                codes.append("very_low_ttc")
                score += weights["very_low_ttc"]

        # --- PET (zone-based; best applicable record for this pair) ---
        pair_ids = frozenset([a["track_id"], b["track_id"]])
        best_pet, pet_zone = None, None
        simultaneous = False
        for p in pet_by_pair.get(pair_ids, []):
            if p["applicable"]:
                if best_pet is None or p["pet_s"] < best_pet:
                    best_pet, pet_zone = p["pet_s"], p["zone_id"]
            elif p.get("reason") == "simultaneous_occupancy":
                simultaneous, pet_zone = True, p["zone_id"]
        if simultaneous:
            codes.append("simultaneous_occupancy")
            score += weights["simultaneous_occupancy"]
        elif best_pet is not None and best_pet < rules["pet_trigger_s"]:
            codes.append("low_pet")
            score += weights["low_pet"]
            if best_pet < 0.5:
                codes.append("very_low_pet")
                score += weights["very_low_pet"]

        # --- separation ---
        sep = pa.get("min_separation_m")
        if sep is not None and sep < rules["separation_trigger_m"]:
            codes.append("low_separation")
            score += weights["low_separation"]
            times.append(pa["t_min_separation_s"])

        # nothing kinematic fired -> not an event, regardless of who was involved
        if not codes:
            continue

        # --- modifiers (only ON TOP of a kinematic trigger) ---
        rel = pa.get("rel_speed_at_min_sep_mps")
        if rel is not None and rel > rules["rel_speed_bonus_mps"]:
            codes.append("high_rel_speed")
            score += weights["high_rel_speed"]
        classes = {a["cls"], b["cls"]}
        if "person" in classes:
            codes.append("pedestrian_involved")
            score += weights["pedestrian_involved"]
        if classes & {"motorcycle", "bicycle"}:
            codes.append("two_wheeler_involved")
            score += weights["two_wheeler_involved"]

        t_anchor = pa.get("t_min_separation_s") or (times[0] if times else 0.0)
        for tid in (a["track_id"], b["track_id"]):
            for ep in braking_by_track.get(tid, []):
                if abs(ep["t_start_s"] - t_anchor) <= rules["hard_braking_window_s"]:
                    codes.append("hard_braking_near_conflict")
                    score += weights["hard_braking_near_conflict"]
                    notes.append(f"track {tid} braked {ep['peak_decel_mps2']} m/s^2 "
                                 f"at t={ep['t_start_s']}s")
                    break

        severity = _severity(score, bands)
        if severity is None:
            continue   # fired a trigger but total weight below the lowest band

        times.append(t_anchor)
        t0, t1 = min(times) - 1.0, max(times) + 1.0
        events.append(ConflictEvent(
            event_id=uuid.uuid4().hex[:12],
            t_start_s=round(max(t0, 0.0), 3),
            t_end_s=round(t1, 3),
            road_user_a=a, road_user_b=b,
            metrics={
                "min_ttc_s": ttc,
                "pet_s": best_pet,
                "min_separation_m": sep,
                "rel_speed_at_min_sep_mps": rel,
                "conflict_angle_class": pa.get("conflict_angle_class"),
                "ttc_not_applicable_reasons": pa.get("ttc_reasons") or {},
            },
            reason_codes=codes,
            score=round(score, 2),
            severity=severity,
            thresholds_profile_id=profile_id,
            zone_id=pet_zone,
            notes=notes,
        ))

    events.sort(key=lambda e: -e.score)
    log.info("near-miss engine: %d events from %d analyzable pairs (profile=%s)",
             len(events), sum(1 for p in pairs if p.get("analyzable")), profile_id)
    return events
