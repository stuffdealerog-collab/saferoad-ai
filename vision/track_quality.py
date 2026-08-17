"""Milestone 1 — track quality gate (tech plan v2 §5).

Garbage tracks must never reach safety analysis. A track enters analysis only if:

- duration >= min_track_duration_s AND n_points >= min_track_points;
- mean detection confidence >= per-class threshold;
- no physically impossible jumps (a jump is a candidate for two objects glued
  into one track -> QUARANTINE, not silent acceptance);
- a gap longer than max_gap_s SPLITS the track into segments — we never
  silently interpolate through an occlusion.

Quarantined tracks are serialized separately: they are the raw material for
the golden set's "tracking failure" category (Milestone 3).

NOTE on units: in Milestone 1 there is no calibration yet, so the teleport
check is done in image space, normalized by the object's own bbox diagonal
(scale-invariant proxy). After Milestone 2 a physical m/s check per class is
added on ground-plane tracks. The thresholds live in
configs/thresholds/*.yaml and are marked experimental.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.log import get_logger
from core.types import Detection, Track, TrackPoint

log = get_logger("vision.quality")


@dataclass
class GateConfig:
    min_track_duration_s: float = 1.0
    min_track_points: int = 8
    min_mean_conf: dict = field(default_factory=lambda: {
        "person": 0.35, "bicycle": 0.35, "motorcycle": 0.35,
        "car": 0.40, "bus": 0.40, "truck": 0.40,
    })
    max_gap_s: float = 0.5
    # teleport: bottom-center moved more than K * bbox diagonal between
    # consecutive points, normalized by the actual time step vs median step
    teleport_diag_factor: float = 1.5

    @classmethod
    def from_dict(cls, d: dict) -> "GateConfig":
        cfg = cls()
        for k, v in d.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


@dataclass
class TrackHealth:
    n_raw_tracks: int = 0
    n_segments: int = 0
    n_passed: int = 0
    n_quarantined: int = 0
    n_gap_splits: int = 0
    n_teleports: int = 0
    fragmentation_rate: float = 0.0   # short segments / all segments
    by_class: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__


def group_by_track(
    frames: list[tuple[int, float, list[Detection]]],
) -> tuple[dict[int, list[TrackPoint]], dict[int, str]]:
    """Collect raw tracker output into {track_id: [points sorted by time]}.
    Also returns a majority class vote per track (trackers occasionally flip
    car<->truck frame to frame)."""
    tracks: dict[int, list[TrackPoint]] = {}
    classes: dict[int, dict[str, int]] = {}
    for _frame_idx, _t_s, dets in frames:
        for d in dets:
            if d.track_id is None:
                continue
            tracks.setdefault(d.track_id, []).append(TrackPoint(
                frame_idx=d.frame_idx, t_s=d.t_s,
                x1_px=d.x1_px, y1_px=d.y1_px, x2_px=d.x2_px, y2_px=d.y2_px,
                conf=d.conf,
            ))
            classes.setdefault(d.track_id, {}).setdefault(d.cls, 0)
            classes[d.track_id][d.cls] += 1
    class_votes = {tid: max(votes, key=votes.get) for tid, votes in classes.items()}
    for pts in tracks.values():
        pts.sort(key=lambda p: p.t_s)
    return tracks, class_votes


def split_on_gaps(track_id: int, cls: str, points: list[TrackPoint], max_gap_s: float) -> list[Track]:
    """Cut a track wherever consecutive points are further apart than max_gap_s."""
    segments: list[Track] = []
    current: list[TrackPoint] = []
    seg_idx = 0
    for p in points:
        if current and (p.t_s - current[-1].t_s) > max_gap_s:
            segments.append(Track(track_id=track_id, segment=seg_idx, cls=cls, points=current))
            seg_idx += 1
            current = []
        current.append(p)
    if current:
        segments.append(Track(track_id=track_id, segment=seg_idx, cls=cls, points=current))
    return segments


def find_teleports(track: Track, cfg: GateConfig) -> list[int]:
    """Indices where the bottom-center jumped implausibly far in one step.
    Distance is normalized by bbox diagonal and by the local time step, so the
    check is scale- and framerate-invariant."""
    bad: list[int] = []
    pts = track.points
    if len(pts) < 3:
        return bad
    steps = [b.t_s - a.t_s for a, b in zip(pts, pts[1:]) if b.t_s > a.t_s]
    if not steps:
        return bad
    median_step = sorted(steps)[len(steps) // 2]
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        dt = b.t_s - a.t_s
        if dt <= 0:
            continue
        ax, ay = a.bottom_center_px
        bx, by = b.bottom_center_px
        dist = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        scale = max((a.diag_px + b.diag_px) / 2.0, 1.0)
        # allowed movement grows linearly with the time step
        allowed = cfg.teleport_diag_factor * scale * max(dt / median_step, 1.0)
        if dist > allowed:
            bad.append(i)
    return bad


def apply_gate(
    frames: list[tuple[int, float, list[Detection]]],
    cfg: GateConfig,
) -> tuple[list[Track], list[Track], TrackHealth]:
    """Returns (passed, quarantined, health). Every rejection carries a reason —
    nothing is dropped silently (tech plan principle #10)."""
    raw, class_votes = group_by_track(frames)
    health = TrackHealth(n_raw_tracks=len(raw))
    passed: list[Track] = []
    quarantined: list[Track] = []

    for tid, points in raw.items():
        cls = class_votes.get(tid, "car")
        segments = split_on_gaps(tid, cls, points, cfg.max_gap_s)
        if len(segments) > 1:
            health.n_gap_splits += len(segments) - 1
        for seg in segments:
            health.n_segments += 1
            flags: list[str] = []
            if seg.duration_s < cfg.min_track_duration_s:
                flags.append(f"too_short: {seg.duration_s:.2f}s < {cfg.min_track_duration_s}s")
            if seg.n_points < cfg.min_track_points:
                flags.append(f"too_few_points: {seg.n_points} < {cfg.min_track_points}")
            min_conf = cfg.min_mean_conf.get(seg.cls, 0.4)
            if seg.mean_conf < min_conf:
                flags.append(f"low_conf: {seg.mean_conf:.2f} < {min_conf}")
            teleports = find_teleports(seg, cfg)
            if teleports:
                health.n_teleports += len(teleports)
                flags.append(f"teleport_at_points: {teleports[:10]}")

            seg.quality_flags = flags
            seg.quarantined = bool(flags)
            if flags:
                quarantined.append(seg)
            else:
                passed.append(seg)
            health.by_class.setdefault(seg.cls, {"passed": 0, "quarantined": 0})
            health.by_class[seg.cls]["quarantined" if flags else "passed"] += 1

    health.n_passed = len(passed)
    health.n_quarantined = len(quarantined)
    short = sum(1 for t in passed + quarantined if t.duration_s < cfg.min_track_duration_s)
    health.fragmentation_rate = round(short / health.n_segments, 3) if health.n_segments else 0.0

    log.info(
        "gate: %d raw tracks -> %d segments; %d passed, %d quarantined "
        "(%d gap splits, %d teleports, fragmentation %.1f%%)",
        health.n_raw_tracks, health.n_segments, health.n_passed,
        health.n_quarantined, health.n_gap_splits, health.n_teleports,
        health.fragmentation_rate * 100,
    )
    return passed, quarantined, health
