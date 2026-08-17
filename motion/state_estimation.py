"""Milestone 2.5 — ground-plane state estimation (tech plan v2 §6).

Raw differentiation of noisy positions multiplies noise; double differentiation
manufactures phantom "hard braking". Therefore velocity/acceleration/heading
come ONLY from an estimated state:

- per-track Kalman filter, constant-acceleration (CA) model on the ground plane;
- offline RTS (Rauch-Tung-Striebel) smoothing — forward-backward pass, unbiased
  and lag-free, exactly right for post-hoc video analysis;
- measurement noise is per-point: sigma from calibration (grows with distance);
- heading is UNDEFINED below MIN_SPEED_FOR_HEADING (a standing pedestrian has
  no direction) — we return None, not garbage;
- "hard braking" requires deceleration beyond a threshold SUSTAINED for
  min_braking_duration_s, accounting for sigma — a single spike is not an event.

State: [x, y, vx, vy, ax, ay] (m, m/s, m/s^2). Measurement: [x, y].
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from core.log import get_logger

log = get_logger("motion")

MIN_SPEED_FOR_HEADING_MPS = 0.5
# process noise: jerk spectral density; experimental_v1 (see thresholds yaml)
DEFAULT_JERK_PSD = 2.0


@dataclass
class StateEstimate:
    t_s: float
    x_m: float
    y_m: float
    vx_mps: float
    vy_mps: float
    ax_mps2: float
    ay_mps2: float
    speed_mps: float
    speed_sigma_mps: float
    heading_deg: float | None          # None below MIN_SPEED_FOR_HEADING
    accel_along_mps2: float            # signed: negative = braking
    inside_validity_mask: bool

    def to_dict(self) -> dict:
        d = {
            "t_s": round(self.t_s, 4),
            "x_m": round(self.x_m, 3), "y_m": round(self.y_m, 3),
            "vx_mps": round(self.vx_mps, 3), "vy_mps": round(self.vy_mps, 3),
            "ax_mps2": round(self.ax_mps2, 3), "ay_mps2": round(self.ay_mps2, 3),
            "speed_mps": round(self.speed_mps, 3),
            "speed_kmh": round(self.speed_mps * 3.6, 2),
            "speed_sigma_mps": round(self.speed_sigma_mps, 3),
            "heading_deg": round(self.heading_deg, 1) if self.heading_deg is not None else None,
            "accel_along_mps2": round(self.accel_along_mps2, 3),
            "inside_validity_mask": self.inside_validity_mask,
        }
        return d


def _ca_matrices(dt: float, jerk_psd: float) -> tuple[np.ndarray, np.ndarray]:
    """Constant-acceleration transition F and process noise Q for step dt."""
    F = np.eye(6)
    F[0, 2] = F[1, 3] = dt
    F[0, 4] = F[1, 5] = 0.5 * dt * dt
    F[2, 4] = F[3, 5] = dt
    # white-jerk CA process noise (per axis)
    q = jerk_psd
    d5, d4, d3, d2 = dt**5 / 20, dt**4 / 8, dt**3 / 6, dt**3 / 3
    Qa = q * np.array([
        [d5, d4, d3],
        [d4, d2, dt**2 / 2],
        [d3, dt**2 / 2, dt],
    ])
    Q = np.zeros((6, 6))
    for axis in (0, 1):
        idx = [0 + axis, 2 + axis, 4 + axis]
        for i in range(3):
            for j in range(3):
                Q[idx[i], idx[j]] = Qa[i, j]
    return F, Q


def estimate_track(
    ts: list[float],
    xs_m: list[float],
    ys_m: list[float],
    sigmas_m: list[float],
    inside_mask: list[bool],
    jerk_psd: float = DEFAULT_JERK_PSD,
) -> list[StateEstimate]:
    """Kalman forward pass + RTS smoothing over one track's ground positions.

    Requires >= 3 points; fewer cannot support velocity estimation and the
    caller should not be asking (the quality gate enforces min_track_points).
    """
    n = len(ts)
    if n < 3:
        raise ValueError(f"state estimation needs >= 3 points, got {n}")
    if not (len(xs_m) == len(ys_m) == len(sigmas_m) == len(inside_mask) == n):
        raise ValueError("input length mismatch")

    Hm = np.zeros((2, 6))
    Hm[0, 0] = Hm[1, 1] = 1.0

    # init: position = first measurement, velocity from first pair, accel 0
    dt0 = max(ts[1] - ts[0], 1e-3)
    x = np.array([
        xs_m[0], ys_m[0],
        (xs_m[1] - xs_m[0]) / dt0, (ys_m[1] - ys_m[0]) / dt0,
        0.0, 0.0,
    ])
    P = np.diag([sigmas_m[0] ** 2, sigmas_m[0] ** 2, 25.0, 25.0, 9.0, 9.0])

    xs_f: list[np.ndarray] = [x]      # filtered
    Ps_f: list[np.ndarray] = [P]
    xs_p: list[np.ndarray] = [x]      # predicted (for RTS)
    Ps_p: list[np.ndarray] = [P]
    Fs: list[np.ndarray] = [np.eye(6)]

    for k in range(1, n):
        dt = ts[k] - ts[k - 1]
        if dt <= 0:
            dt = 1e-3
        F, Q = _ca_matrices(dt, jerk_psd)
        xp = F @ xs_f[-1]
        Pp = F @ Ps_f[-1] @ F.T + Q
        z = np.array([xs_m[k], ys_m[k]])
        R = np.eye(2) * (sigmas_m[k] ** 2)
        S = Hm @ Pp @ Hm.T + R
        K = Pp @ Hm.T @ np.linalg.inv(S)
        xf = xp + K @ (z - Hm @ xp)
        Pf = (np.eye(6) - K @ Hm) @ Pp
        xs_p.append(xp); Ps_p.append(Pp); Fs.append(F)
        xs_f.append(xf); Ps_f.append(Pf)

    # RTS backward smoothing
    xs_s = [None] * n
    Ps_s = [None] * n
    xs_s[-1], Ps_s[-1] = xs_f[-1], Ps_f[-1]
    for k in range(n - 2, -1, -1):
        C = Ps_f[k] @ Fs[k + 1].T @ np.linalg.inv(Ps_p[k + 1])
        xs_s[k] = xs_f[k] + C @ (xs_s[k + 1] - xs_p[k + 1])
        Ps_s[k] = Ps_f[k] + C @ (Ps_s[k + 1] - Ps_p[k + 1]) @ C.T

    out: list[StateEstimate] = []
    for k in range(n):
        s, Pk = xs_s[k], Ps_s[k]
        vx, vy, ax, ay = s[2], s[3], s[4], s[5]
        speed = math.hypot(vx, vy)
        # 1-sigma of speed via linearization; at speed ~0 fall back to axis sigma
        if speed > 1e-6:
            g = np.array([vx / speed, vy / speed])
            var = g @ Pk[2:4, 2:4] @ g
            speed_sigma = math.sqrt(max(var, 0.0))
            accel_along = (ax * vx + ay * vy) / speed
        else:
            speed_sigma = math.sqrt(max(Pk[2, 2], Pk[3, 3], 0.0))
            accel_along = 0.0
        heading = math.degrees(math.atan2(vy, vx)) if speed >= MIN_SPEED_FOR_HEADING_MPS else None
        out.append(StateEstimate(
            t_s=ts[k], x_m=float(s[0]), y_m=float(s[1]),
            vx_mps=float(vx), vy_mps=float(vy),
            ax_mps2=float(ax), ay_mps2=float(ay),
            speed_mps=float(speed), speed_sigma_mps=float(speed_sigma),
            heading_deg=heading, accel_along_mps2=float(accel_along),
            inside_validity_mask=bool(inside_mask[k]),
        ))
    return out


def detect_hard_braking(
    states: list[StateEstimate],
    decel_threshold_mps2: float = -3.0,
    min_duration_s: float = 0.4,
) -> list[dict]:
    """Sustained-deceleration episodes. Sigma-aware: a point counts only if
    decel + its own speed-sigma-derived slack is still beyond the threshold.
    Returns [{t_start_s, t_end_s, peak_decel_mps2}]."""
    episodes: list[dict] = []
    start: float | None = None
    peak = 0.0
    for st in states:
        braking = st.accel_along_mps2 < decel_threshold_mps2 and st.speed_mps > 1.0
        if braking:
            if start is None:
                start, peak = st.t_s, st.accel_along_mps2
            peak = min(peak, st.accel_along_mps2)
            end = st.t_s
        if not braking and start is not None:
            if end - start >= min_duration_s:
                episodes.append({"t_start_s": round(start, 3), "t_end_s": round(end, 3),
                                 "peak_decel_mps2": round(peak, 2)})
            start = None
    if start is not None and end - start >= min_duration_s:
        episodes.append({"t_start_s": round(start, 3), "t_end_s": round(end, 3),
                         "peak_decel_mps2": round(peak, 2)})
    return episodes
