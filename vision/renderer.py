"""Milestone 1 — annotated evidence video.

Draws per-frame: bboxes, track ids, class labels, trajectory trails
(bottom-center history). Quarantined tracks are drawn gray/dashed so a
reviewer SEES what the gate rejected — rejections are inspectable, not hidden.
"""
from __future__ import annotations

from pathlib import Path

import cv2

from core.log import get_logger
from core.types import Track

log = get_logger("vision.renderer")

CLASS_COLORS = {  # BGR
    "person": (80, 200, 255),
    "bicycle": (255, 200, 80),
    "motorcycle": (255, 120, 200),
    "car": (120, 220, 120),
    "bus": (90, 90, 230),
    "truck": (200, 160, 90),
}
QUARANTINE_COLOR = (128, 128, 128)
TRAIL_LEN = 30  # points of trajectory history to draw


def _index_tracks_by_frame(tracks: list[Track]) -> dict[int, list[tuple[Track, int]]]:
    """frame_idx -> [(track, point_idx_in_track)]"""
    idx: dict[int, list[tuple[Track, int]]] = {}
    for tr in tracks:
        for i, p in enumerate(tr.points):
            idx.setdefault(p.frame_idx, []).append((tr, i))
    return idx


def render(
    video_path: str | Path,
    pts_map: list[float],
    passed: list[Track],
    quarantined: list[Track],
    out_path: str | Path,
    draw_quarantined: bool = True,
) -> Path:
    out_path = Path(out_path)
    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    frame_index = _index_tracks_by_frame(passed)
    q_index = _index_tracks_by_frame(quarantined) if draw_quarantined else {}

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t_s = pts_map[frame_idx] if frame_idx < len(pts_map) else -1.0

        for tr, i in q_index.get(frame_idx, []):
            p = tr.points[i]
            cv2.rectangle(frame, (int(p.x1_px), int(p.y1_px)), (int(p.x2_px), int(p.y2_px)),
                          QUARANTINE_COLOR, 1)
            cv2.putText(frame, f"Q#{tr.track_id}", (int(p.x1_px), int(p.y1_px) - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, QUARANTINE_COLOR, 1)

        for tr, i in frame_index.get(frame_idx, []):
            p = tr.points[i]
            color = CLASS_COLORS.get(tr.cls, (255, 255, 255))
            cv2.rectangle(frame, (int(p.x1_px), int(p.y1_px)), (int(p.x2_px), int(p.y2_px)), color, 2)
            cv2.putText(frame, f"{tr.cls}#{tr.track_id} {p.conf:.2f}",
                        (int(p.x1_px), max(int(p.y1_px) - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            trail = tr.points[max(0, i - TRAIL_LEN): i + 1]
            for a, b in zip(trail, trail[1:]):
                ax, ay = a.bottom_center_px
                bx, by = b.bottom_center_px
                cv2.line(frame, (int(ax), int(ay)), (int(bx), int(by)), color, 2)

        cv2.putText(frame, f"t={t_s:.2f}s  frame={frame_idx}", (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()
    log.info("annotated video written: %s (%d frames)", out_path, frame_idx)
    return out_path
