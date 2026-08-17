"""Unit tests for Kalman/RTS state estimation — analytic trajectories + noise.

Tech plan v2 §6 acceptance: synthetic tests pass, and NO phantom hard-braking
on constant-speed motion.
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from motion.state_estimation import (
    MIN_SPEED_FOR_HEADING_MPS,
    detect_hard_braking,
    estimate_track,
)

DT = 0.04  # 25 fps


def constant_velocity_track(v_mps=6.0, n=100, noise_m=0.15, seed=1):
    rng = random.Random(seed)
    ts = [i * DT for i in range(n)]
    xs = [v_mps * t + rng.gauss(0, noise_m) for t in ts]
    ys = [rng.gauss(0, noise_m) for _ in ts]
    sig = [noise_m] * n
    return ts, xs, ys, sig, [True] * n


def test_constant_speed_recovered_within_5pct():
    ts, xs, ys, sig, mask = constant_velocity_track()
    states = estimate_track(ts, xs, ys, sig, mask)
    mid = states[20:-20]  # ignore boundary transients
    mean_speed = sum(s.speed_mps for s in mid) / len(mid)
    assert abs(mean_speed - 6.0) / 6.0 < 0.05


def test_no_phantom_braking_on_constant_speed():
    ts, xs, ys, sig, mask = constant_velocity_track()
    states = estimate_track(ts, xs, ys, sig, mask)
    assert detect_hard_braking(states) == []


def test_real_braking_detected():
    # 8 m/s constant, then brake at -5 m/s^2 to a stop
    ts, xs = [], []
    t, x, v = 0.0, 0.0, 8.0
    for _ in range(150):
        ts.append(t); xs.append(x)
        if t > 2.0 and v > 0:
            v = max(v - 5.0 * DT, 0.0)
        x += v * DT
        t += DT
    n = len(ts)
    states = estimate_track(ts, xs, [0.0] * n, [0.05] * n, [True] * n)
    episodes = detect_hard_braking(states)
    assert episodes, "sustained -5 m/s^2 braking must be detected"
    assert 1.6 < episodes[0]["t_start_s"] < 2.6  # near the true onset t=2.0


def test_heading_undefined_when_stationary():
    n = 60
    ts = [i * DT for i in range(n)]
    rng = random.Random(2)
    xs = [rng.gauss(0, 0.05) for _ in range(n)]   # jitter around a fixed point
    ys = [rng.gauss(0, 0.05) for _ in range(n)]
    states = estimate_track(ts, xs, ys, [0.05] * n, [True] * n)
    mid = states[10:-10]
    assert all(s.heading_deg is None for s in mid if s.speed_mps < MIN_SPEED_FOR_HEADING_MPS)
    assert sum(1 for s in mid if s.heading_deg is None) > len(mid) * 0.8


def test_heading_correct_when_moving():
    ts = [i * DT for i in range(80)]
    xs = [3.0 * t for t in ts]          # +x direction
    ys = [3.0 * t for t in ts]          # +y direction -> 45 deg
    n = len(ts)
    states = estimate_track(ts, xs, ys, [0.05] * n, [True] * n)
    mid = states[20:-20]
    for s in mid:
        assert s.heading_deg is not None
        assert abs(s.heading_deg - 45.0) < 5.0


def test_speed_sigma_grows_with_measurement_noise():
    _, xs, ys, _, mask = constant_velocity_track(noise_m=0.05)
    ts = [i * DT for i in range(len(xs))]
    low = estimate_track(ts, xs, ys, [0.05] * len(ts), mask)
    ts2, xs2, ys2, _, mask2 = constant_velocity_track(noise_m=0.4, seed=3)
    high = estimate_track(ts2, xs2, ys2, [0.4] * len(ts2), mask2)
    assert (sum(s.speed_sigma_mps for s in high[20:-20]) / len(high[20:-20]) >
            sum(s.speed_sigma_mps for s in low[20:-20]) / len(low[20:-20]))


def test_too_few_points_rejected():
    with pytest.raises(ValueError):
        estimate_track([0.0, 0.04], [0, 1], [0, 0], [0.1, 0.1], [True, True])
