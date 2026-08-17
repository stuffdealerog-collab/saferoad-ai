"""Milestone 6 — evidence clips (tech plan v2 §10 of v1: visual evidence).

For every ConflictEvent, cut the event window from the source video and render:
- the two participants highlighted (colored boxes + trails), other tracks dimmed;
- the conflict zone polygon (ground -> image via inverse homography);
- a metrics card: ids/classes, TTC/PET/min separation, severity, reason codes;
- a progress bar over the event window.

The clip must let a reviewer decide whether the event is real WITHOUT reading
any code — this is the artifact government users actually trust.
"""
from __future__ import annotations

from bisect import bisect_left
from pathlib import Path

import cv2
import numpy as np

from core.log import get_logger
from core.types import Track
from vision.calibration import CameraCalibration
from vision.renderer import CLASS_COLORS

log = get_logger("vision.evidence")

SEVERITY_COLORS = {  # BGR
    "critical": (60, 60, 220),
    "high": (50, 130, 240),
    "medium": (60, 200, 240),
    "low": (160, 160, 160),
}
DIM_COLOR = (90, 90, 90)
PAD_S = 0.5   # extra context around the event window


def _tracks_by_frame(tracks: list[Track]) -> dict[int, list[tuple[Track, int]]]:
    idx: dict[int, list[tuple[Track, int]]] = {}
    for tr in tracks:
        for i, p in enumerate(tr.points):
            idx.setdefault(p.frame_idx, []).append((tr, i))
    return idx


def _zone_polygon_px(calibration: CameraCalibration, polygon_m: np.ndarray) -> np.ndarray | None:
    try:
        Hinv = np.linalg.inv(calibration.H)
        pts = polygon_m.reshape(-1, 1, 2).astype(np.float64)
        img = cv2.perspectiveTransform(pts, Hinv).reshape(-1, 2)
        return img.astype(np.int32)
    except np.linalg.LinAlgError:
        log.error("homography not invertible — zone overlay skipped")
        return None


def _fmt(v, unit=""):
    return f"{v}{unit}" if v is not None else "n/a"


def render_event_clip(
    video_path: str | Path,
    pts_map: list[float],
    event: dict,
    tracks: list[Track],
    calibration: CameraCalibration | None,
    zones_by_id: dict[str, np.ndarray],   # zone_id -> polygon_m
    out_path: str | Path,
) -> Path | None:
    t0 = max(event["t_start_s"] - PAD_S, 0.0)
    t1 = min(event["t_end_s"] + PAD_S, pts_map[-1])
    f0 = bisect_left(pts_map, t0)
    f1 = bisect_left(pts_map, t1)
    if f1 <= f0:
        log.error("event %s: empty frame window [%s..%s] — clip skipped",
                  event["event_id"], t0, t1)
        return None

    participants = {
        (event["road_user_a"]["track_id"], event["road_user_a"]["segment"]),
        (event["road_user_b"]["track_id"], event["road_user_b"]["segment"]),
    }
    frame_index = _tracks_by_frame(tracks)
    zone_px = None
    if calibration is not None and event.get("zone_id") in zones_by_id:
        zone_px = _zone_polygon_px(calibration, zones_by_id[event["zone_id"]])

    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    out_path = Path(out_path)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)

    sev = event["severity"]
    sev_color = SEVERITY_COLORS.get(sev, (255, 255, 255))
    m = event["metrics"]
    card_lines = [
        f"EVENT {event['event_id']}  [{sev.upper()}]  score={event['score']}",
        f"{event['road_user_a']['cls']}#{event['road_user_a']['track_id']}"
        f"  vs  {event['road_user_b']['cls']}#{event['road_user_b']['track_id']}"
        f"   type: {_fmt(m.get('conflict_angle_class'))}",
        f"TTC: {_fmt(m.get('min_ttc_s'), 's')}   PET: {_fmt(m.get('pet_s'), 's')}"
        f"   min dist: {_fmt(m.get('min_separation_m'), 'm')}"
        f"   rel speed: {_fmt(m.get('rel_speed_at_min_sep_mps'), ' m/s')}",
        "reasons: " + ", ".join(event["reason_codes"]),
        f"profile: {event['thresholds_profile_id']} (EXPERIMENTAL)",
    ]

    for fi in range(f0, f1 + 1):
        ok, frame = cap.read()
        if not ok:
            break
        t = pts_map[fi] if fi < len(pts_map) else t1

        if zone_px is not None:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [zone_px], (0, 0, 160))
            frame = cv2.addWeighted(overlay, 0.18, frame, 0.82, 0)
            cv2.polylines(frame, [zone_px], True, (0, 0, 200), 2)

        for tr, i in frame_index.get(fi, []):
            p = tr.points[i]
            key = (tr.track_id, tr.segment)
            if key in participants:
                color = CLASS_COLORS.get(tr.cls, (255, 255, 255))
                cv2.rectangle(frame, (int(p.x1_px), int(p.y1_px)),
                              (int(p.x2_px), int(p.y2_px)), color, 3)
                cv2.putText(frame, f"{tr.cls}#{tr.track_id}",
                            (int(p.x1_px), max(int(p.y1_px) - 8, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
                trail = tr.points[max(0, i - 40): i + 1]
                for a, b in zip(trail, trail[1:]):
                    ax, ay = a.bottom_center_px
                    bx, by = b.bottom_center_px
                    cv2.line(frame, (int(ax), int(ay)), (int(bx), int(by)), color, 2)
            else:
                cv2.rectangle(frame, (int(p.x1_px), int(p.y1_px)),
                              (int(p.x2_px), int(p.y2_px)), DIM_COLOR, 1)

        # metrics card
        card_h = 24 + 22 * len(card_lines)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, card_h), (25, 25, 25), -1)
        frame = cv2.addWeighted(overlay, 0.75, frame, 0.25, 0)
        cv2.rectangle(frame, (0, 0), (8, card_h), sev_color, -1)
        for li, line in enumerate(card_lines):
            cv2.putText(frame, line, (20, 24 + 22 * li),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                        sev_color if li == 0 else (230, 230, 230), 1, cv2.LINE_AA)

        # progress bar + clock
        prog = (t - t0) / max(t1 - t0, 1e-6)
        cv2.rectangle(frame, (0, h - 6), (int(w * prog), h), sev_color, -1)
        cv2.putText(frame, f"t={t:.2f}s", (w - 120, h - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        writer.write(frame)

    cap.release()
    writer.release()
    log.info("evidence clip: %s (%.1fs window)", out_path.name, t1 - t0)
    return out_path


def render_all_events(
    video_path: str | Path,
    pts_map: list[float],
    events: list[dict],
    tracks: list[Track],
    calibration: CameraCalibration | None,
    zones_by_id: dict[str, np.ndarray],
    out_dir: str | Path,
) -> list[dict]:
    """Render every event's clip; returns [{event_id, clip}] manifest."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for ev in events:
        name = f"event_{ev['severity']}_{ev['event_id']}.mp4"
        clip = render_event_clip(video_path, pts_map, ev, tracks,
                                 calibration, zones_by_id, out_dir / name)
        if clip is not None:
            manifest.append({"event_id": ev["event_id"], "clip": name})
    return manifest
