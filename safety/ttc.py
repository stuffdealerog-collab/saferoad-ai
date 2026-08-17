"""Milestone 4 — Time To Collision with explicit applicability bounds.

TTC answers: "if both road users keep their CURRENT velocity, in how many
seconds do their safety envelopes touch?" It is only meaningful when its
assumptions hold (tech plan v2 §7). This module therefore returns a typed
result: a value OR a not-applicable reason — never a garbage number.

Applicability guards:
- both objects moving toward each other (closing: d/dt|r| < 0);
- relative speed above MIN_REL_SPEED (below it TTC explodes numerically);
- a collision course actually exists (miss distance < combined radius);
- constant-velocity extrapolation horizon MAX_TTC_S — beyond it the
  prediction is fiction and we say so.

Units: meters, seconds, m/s. Ground plane only — never pixels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MIN_REL_SPEED_MPS = 0.5
MAX_TTC_S = 5.0

# effective safety radius per class (half-envelope, meters) — experimental_v1
CLASS_RADIUS_M = {
    "person": 0.4, "bicycle": 0.5, "motorcycle": 0.5,
    "car": 1.0, "bus": 1.8, "truck": 1.6,
}


@dataclass
class TTCResult:
    applicable: bool
    ttc_s: float | None = None
    reason: str | None = None           # why not applicable
    t_closest_s: float | None = None    # time to minimum separation (CV model)
    min_separation_m: float | None = None


def instantaneous_ttc(
    rx_m: float, ry_m: float,          # position of B relative to A (m)
    rvx_mps: float, rvy_mps: float,    # velocity of B relative to A (m/s)
    radius_sum_m: float,
) -> TTCResult:
    """Constant-velocity TTC for one instant. r is the current relative
    position; collision when |r + v*t| = radius_sum."""
    dist = math.hypot(rx_m, ry_m)
    if dist <= radius_sum_m:
        # envelopes already touch: TTC=0 (degenerate but must not crash)
        return TTCResult(True, ttc_s=0.0, t_closest_s=0.0, min_separation_m=dist)

    rel_speed = math.hypot(rvx_mps, rvy_mps)
    if rel_speed < MIN_REL_SPEED_MPS:
        return TTCResult(False, reason=f"rel_speed_below_{MIN_REL_SPEED_MPS}mps")

    r_dot_v = rx_m * rvx_mps + ry_m * rvy_mps
    if r_dot_v >= 0:
        return TTCResult(False, reason="not_closing")

    t_closest = -r_dot_v / (rel_speed ** 2)
    cx, cy = rx_m + rvx_mps * t_closest, ry_m + rvy_mps * t_closest
    min_sep = math.hypot(cx, cy)

    # collision course? solve |r + v t|^2 = radius_sum^2
    a = rel_speed ** 2
    b = 2.0 * r_dot_v
    c = dist ** 2 - radius_sum_m ** 2
    disc = b * b - 4 * a * c
    if disc < 0:
        return TTCResult(False, reason="no_collision_course",
                         t_closest_s=t_closest, min_separation_m=min_sep)
    ttc = (-b - math.sqrt(disc)) / (2 * a)   # first (earliest) touching time
    if ttc < 0:
        return TTCResult(False, reason="collision_in_past",
                         t_closest_s=t_closest, min_separation_m=min_sep)
    if ttc > MAX_TTC_S:
        return TTCResult(False, reason=f"beyond_horizon_{MAX_TTC_S}s",
                         t_closest_s=t_closest, min_separation_m=min_sep)
    return TTCResult(True, ttc_s=ttc, t_closest_s=t_closest, min_separation_m=min_sep)


def radius_for(cls_a: str, cls_b: str) -> float:
    return CLASS_RADIUS_M.get(cls_a, 1.0) + CLASS_RADIUS_M.get(cls_b, 1.0)
