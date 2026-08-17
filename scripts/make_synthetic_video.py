"""Generate a synthetic intersection video WITH analytically known ground truth.

Purpose (tech plan v2, principle #7): exercise everything downstream of the
detector — timing, tracking-data structures, quality gate, renderer — against
known truth. The YOLO detector is NOT tested here (rectangles are not cars);
it is exercised separately on real imagery. The pipeline consumes this via
``--tracker fake --script <detections.json>``.

Scenario (1280x720 @ 25fps, 12s):
  - car #1: crosses left->right at constant speed (clean track);
  - car #2: crosses top->bottom, DISAPPEARS for 1.0s mid-way (gap split case);
  - person #3: walks along the crossing slowly (clean, small bbox);
  - ghost #4: a "glued" track that teleports across the frame (quarantine case);
  - flicker #5: exists for 0.3s only (too-short case).

Outputs: sample_data/synthetic_intersection.mp4, sample_data/synthetic_detections.json,
         sample_data/synthetic_truth.json (expected gate outcomes for tests).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

W, H, FPS, DUR_S = 1280, 720, 25.0, 12.0
N_FRAMES = int(DUR_S * FPS)


def draw_scene(frame: np.ndarray) -> None:
    frame[:] = (60, 60, 60)
    cv2.rectangle(frame, (0, 280), (W, 440), (80, 80, 80), -1)      # horizontal road
    cv2.rectangle(frame, (560, 0), (720, H), (80, 80, 80), -1)      # vertical road
    for x in range(0, W, 80):                                        # lane dashes
        cv2.line(frame, (x, 360), (x + 40, 360), (200, 200, 200), 2)
    for y in range(0, H, 80):
        cv2.line(frame, (640, y), (640, y + 40), (200, 200, 200), 2)
    for i in range(6):                                               # zebra
        cv2.rectangle(frame, (470 + i * 14, 285), (478 + i * 14, 435), (220, 220, 220), -1)


def actors(t: float) -> list[dict]:
    """Ground-truth boxes at time t (seconds). Returns list of dicts."""
    out = []
    # car 1: left->right, 90 px/s, y center 320, box 90x50
    x = -100 + 120.0 * t
    if -100 <= x <= W + 50:
        out.append(dict(track_id=1, cls="car", x1=x, y1=300, x2=x + 90, y2=350, conf=0.9))
    # car 2: top->bottom 80 px/s, disappears t in [5.0, 6.0) (occlusion)
    y = -80 + 80.0 * t
    if -80 <= y <= H + 50 and not (5.0 <= t < 6.0):
        out.append(dict(track_id=2, cls="car", x1=600, y1=y, x2=655, y2=y + 95, conf=0.85))
    # person 3: walks down the zebra, 30 px/s
    py = 260 + 30.0 * t
    if py <= 460:
        out.append(dict(track_id=3, cls="person", x1=500, y1=py, x2=525, y2=py + 55, conf=0.8))
    # ghost 4: teleports between two corners every second (glued-track case)
    if 2.0 <= t <= 9.0:
        if int(t) % 2 == 0:
            out.append(dict(track_id=4, cls="car", x1=100, y1=500, x2=180, y2=550, conf=0.7))
        else:
            out.append(dict(track_id=4, cls="car", x1=1100, y1=100, x2=1180, y2=150, conf=0.7))
    # flicker 5: exists 0.3s only
    if 7.0 <= t < 7.3:
        out.append(dict(track_id=5, cls="person", x1=900, y1=600, x2=925, y2=650, conf=0.6))
    return out


def main() -> None:
    out_dir = ROOT / "sample_data"
    out_dir.mkdir(exist_ok=True)
    video_path = out_dir / "synthetic_intersection.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))

    script: dict[int, list[dict]] = {}
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    for i in range(N_FRAMES):
        t = i / FPS
        draw_scene(frame)
        dets = actors(t)
        for d in dets:
            color = (0, 200, 255) if d["cls"] == "person" else (200, 120, 60)
            cv2.rectangle(frame, (int(d["x1"]), int(d["y1"])), (int(d["x2"]), int(d["y2"])), color, -1)
        script[i] = dets
        writer.write(frame)
    writer.release()

    (out_dir / "synthetic_detections.json").write_text(json.dumps(script))
    truth = {
        "expected_passed_track_ids": [1, 3],
        "expected_gap_split_track_id": 2,        # must yield 2 passed segments
        "expected_quarantined_track_ids": [4],   # teleports
        "expected_too_short_track_ids": [5],
        "fps": FPS, "n_frames": N_FRAMES,
        "car1_speed_px_s": 120.0, "car2_speed_px_s": 80.0, "person3_speed_px_s": 30.0,
    }
    (out_dir / "synthetic_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"written: {video_path} ({N_FRAMES} frames), detections script, truth")


if __name__ == "__main__":
    main()
