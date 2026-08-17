"""Unit tests for TTC and PET — analytic cases with exact answers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from geometry.zones import Occupancy, Zone, occupancy_intervals
from safety.pet import pet_between
from safety.ttc import instantaneous_ttc
import numpy as np


# ---------------- TTC ----------------

def test_head_on_collision_course():
    # B is 20m ahead, closing at 10 m/s, radius sum 2m -> touch at (20-2)/10 = 1.8s
    r = instantaneous_ttc(20.0, 0.0, -10.0, 0.0, 2.0)
    assert r.applicable
    assert abs(r.ttc_s - 1.8) < 1e-9


def test_parallel_same_speed_not_applicable():
    r = instantaneous_ttc(5.0, 0.0, 0.0, 0.0, 2.0)
    assert not r.applicable
    assert "rel_speed" in r.reason


def test_receding_not_applicable():
    r = instantaneous_ttc(10.0, 0.0, 5.0, 0.0, 2.0)
    assert not r.applicable
    assert r.reason == "not_closing"


def test_crossing_miss_reports_min_separation():
    # B passes 5m to the side: closing but no collision course
    r = instantaneous_ttc(10.0, 5.0, -10.0, 0.0, 2.0)
    assert not r.applicable
    assert r.reason == "no_collision_course"
    assert abs(r.min_separation_m - 5.0) < 1e-9
    assert abs(r.t_closest_s - 1.0) < 1e-9


def test_beyond_horizon_refused():
    # collision course but 100m away at 1 m/s -> 98s >> horizon
    r = instantaneous_ttc(100.0, 0.0, -1.0, 0.0, 2.0)
    assert not r.applicable
    assert "beyond_horizon" in r.reason


def test_already_touching_gives_zero():
    r = instantaneous_ttc(1.0, 0.0, -1.0, 0.0, 2.0)
    assert r.applicable and r.ttc_s == 0.0


# ---------------- zones / occupancy ----------------

def square_zone():
    return Zone("z1", "junction", np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float))


def test_occupancy_interval_detected():
    z = square_zone()
    ts = [i * 0.1 for i in range(41)]
    xs = [-2.0 + 0.1 * i for i in range(41)]   # crosses zone x in [-1,1] -> t in [1.0..3.0]
    ys = [0.0] * 41
    occ = occupancy_intervals(z, 1, 0, "car", ts, xs, ys)
    assert len(occ) == 1
    assert occ[0].enter_observed and occ[0].exit_observed
    assert abs(occ[0].t_enter_s - 1.1) < 0.11   # first sample strictly inside
    assert abs(occ[0].t_exit_s - 2.9) < 0.11


def test_track_ending_inside_zone_flags_unobserved_exit():
    z = square_zone()
    ts = [i * 0.1 for i in range(15)]
    xs = [-2.0 + 0.1 * i for i in range(15)]   # ends at x=-0.6, INSIDE the zone
    occ = occupancy_intervals(z, 2, 0, "car", ts, xs, [0.0] * 15)
    assert len(occ) == 1
    assert not occ[0].exit_observed


def test_track_starting_inside_zone_flags_unobserved_entry():
    z = square_zone()
    ts = [i * 0.1 for i in range(15)]
    xs = [0.0 + 0.1 * i for i in range(15)]    # starts at x=0, inside
    occ = occupancy_intervals(z, 3, 0, "person", ts, xs, [0.0] * 15)
    assert not occ[0].enter_observed


# ---------------- PET ----------------

def occ(tid, t_in, t_out, enter_obs=True, exit_obs=True):
    return Occupancy("z1", tid, 0, "car", t_in, t_out, enter_obs, exit_obs)


def test_pet_basic():
    r = pet_between(occ(1, 1.0, 2.0), occ(2, 2.5, 3.5), resolution_s=0.04)
    assert r.applicable and abs(r.pet_s - 0.5) < 1e-9
    assert r.resolution_s == 0.04


def test_pet_order_independent():
    r = pet_between(occ(2, 2.5, 3.5), occ(1, 1.0, 2.0), resolution_s=0.04)
    assert r.applicable and abs(r.pet_s - 0.5) < 1e-9


def test_pet_simultaneous_occupancy_flagged():
    r = pet_between(occ(1, 1.0, 3.0), occ(2, 2.0, 4.0), resolution_s=0.04)
    assert not r.applicable
    assert r.reason == "simultaneous_occupancy"


def test_pet_refuses_truncated_exit():
    """The audit case: first user's track ended inside the zone (occlusion) —
    its 'exit' is fiction and must NOT produce a fake small PET."""
    r = pet_between(occ(1, 1.0, 2.0, exit_obs=False), occ(2, 2.1, 3.0), resolution_s=0.04)
    assert not r.applicable
    assert "unobserved" in r.reason


def test_pet_refuses_unobserved_entry():
    r = pet_between(occ(1, 1.0, 2.0), occ(2, 2.1, 3.0, enter_obs=False), resolution_s=0.04)
    assert not r.applicable


def test_pet_different_zones_raises():
    a = occ(1, 1.0, 2.0)
    b = Occupancy("z2", 2, 0, "car", 2.5, 3.0)
    with pytest.raises(ValueError):
        pet_between(a, b, 0.04)
