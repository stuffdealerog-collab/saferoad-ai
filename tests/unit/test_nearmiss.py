"""Unit tests for the near-miss engine — constructed inputs, known verdicts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from safety.nearmiss import build_events


def pair(tid_a=1, cls_a="car", tid_b=2, cls_b="car", **kw):
    base = {
        "track_a": {"track_id": tid_a, "segment": 0, "cls": cls_a},
        "track_b": {"track_id": tid_b, "segment": 0, "cls": cls_b},
        "overlap_s": 5.0, "analyzable": True,
        "min_separation_m": 10.0, "t_min_separation_s": 3.0,
        "rel_speed_at_min_sep_mps": 5.0, "conflict_angle_class": "crossing",
        "min_ttc_s": None, "t_min_ttc_s": None, "ttc_reasons": {},
    }
    base.update(kw)
    return base


def pet_record(tid_first=1, tid_second=2, pet_s=0.4, applicable=True, reason=None):
    return {
        "applicable": applicable, "zone_id": "z1",
        "first": {"track_id": tid_first, "segment": 0, "exit_observed": True},
        "second": {"track_id": tid_second, "segment": 0, "enter_observed": True},
        "pet_s": pet_s if applicable else None,
        "resolution_s": 0.04, "reason": reason,
    }


def test_no_kinematic_trigger_no_event_even_with_pedestrian():
    """Involvement modifiers must never create an event on their own."""
    events = build_events([pair(cls_b="person")], [], [])
    assert events == []


def test_low_ttc_creates_event_with_reason():
    events = build_events([pair(min_ttc_s=1.5, t_min_ttc_s=2.8)], [], [])
    assert len(events) == 1
    assert "low_ttc" in events[0].reason_codes
    assert events[0].metrics["min_ttc_s"] == 1.5
    assert events[0].thresholds_profile_id == "experimental_v1"


def test_very_low_ttc_escalates():
    ev_low = build_events([pair(min_ttc_s=1.5, t_min_ttc_s=1.0)], [], [])[0]
    ev_very = build_events([pair(min_ttc_s=0.8, t_min_ttc_s=1.0)], [], [])[0]
    assert ev_very.score > ev_low.score
    assert "very_low_ttc" in ev_very.reason_codes


def test_pedestrian_low_pet_reaches_high_severity():
    """The synthetic zebra case shape: low PET + pedestrian involved."""
    events = build_events(
        [pair(cls_b="person", min_separation_m=5.2)],
        [pet_record(tid_first=2, tid_second=1, pet_s=0.4)],
        [],
    )
    assert len(events) == 1
    ev = events[0]
    assert {"low_pet", "very_low_pet", "pedestrian_involved"} <= set(ev.reason_codes)
    # 2.5 + 2.0 + 2.0 = 6.5 -> high (>=5.0, <7.0)
    assert ev.severity == "high"
    assert ev.zone_id == "z1"


def test_simultaneous_occupancy_scores_worse_than_low_pet():
    ev_pet = build_events([pair()], [pet_record(pet_s=1.2)], [])[0]
    ev_sim = build_events(
        [pair()], [pet_record(applicable=False, reason="simultaneous_occupancy")], [])[0]
    assert ev_sim.score > ev_pet.score
    assert "simultaneous_occupancy" in ev_sim.reason_codes


def test_hard_braking_near_conflict_attached():
    braking = [{"track_id": 1, "segment": 0, "cls": "car",
                "episodes": [{"t_start_s": 2.5, "t_end_s": 3.1, "peak_decel_mps2": -4.5}]}]
    events = build_events([pair(min_ttc_s=1.5, t_min_ttc_s=3.0)], [], braking)
    assert "hard_braking_near_conflict" in events[0].reason_codes
    assert events[0].notes  # the braking episode is cited in notes


def test_braking_far_from_conflict_ignored():
    braking = [{"track_id": 1, "segment": 0, "cls": "car",
                "episodes": [{"t_start_s": 20.0, "t_end_s": 21.0, "peak_decel_mps2": -4.5}]}]
    events = build_events([pair(min_ttc_s=1.5, t_min_ttc_s=3.0)], [], braking)
    assert "hard_braking_near_conflict" not in events[0].reason_codes


def test_unanalyzable_pairs_skipped():
    p = pair()
    p["analyzable"] = False
    assert build_events([p], [pet_record(pet_s=0.1)], []) == []


def test_custom_rules_override():
    events = build_events([pair(min_ttc_s=2.5, t_min_ttc_s=1.0)], [], [],
                          rules={"ttc_trigger_s": 3.0})
    assert events and "low_ttc" in events[0].reason_codes


def test_events_sorted_by_score_desc():
    events = build_events(
        [pair(tid_a=1, tid_b=2, min_ttc_s=1.5, t_min_ttc_s=1.0),
         pair(tid_a=3, tid_b=4, cls_b="person", min_ttc_s=0.5, t_min_ttc_s=1.0,
              min_separation_m=1.0)],
        [], [])
    assert len(events) == 2
    assert events[0].score >= events[1].score
    assert events[0].road_user_a["track_id"] == 3
