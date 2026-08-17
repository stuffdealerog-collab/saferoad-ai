"""Milestone 1 — detection + tracking (tech plan v2 §5).

Two implementations behind one interface:

- ``YoloTracker`` — Ultralytics YOLO + ByteTrack/BoT-SORT (production path);
- ``FakeTracker`` — replays scripted detections (synthetic tests, tech plan
  principle #7: synthetic tests for edge cases). The pipeline is identical
  downstream, which is exactly the point.

The tracker yields per-frame lists of ``Detection`` with ``track_id`` set.
Timestamps come ONLY from the ingest PTS map.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Protocol

import cv2

from core.log import get_logger
from core.types import COCO_ROAD_USERS, Detection

log = get_logger("vision.tracker")


class FrameSource:
    """Reads frames with their REAL presentation times (from the ingest PTS map)."""

    def __init__(self, video_path: str | Path, pts_map: list[float]):
        self.video_path = str(video_path)
        self.pts_map = pts_map

    def __iter__(self) -> Iterator[tuple[int, float, "cv2.Mat"]]:
        cap = cv2.VideoCapture(self.video_path)
        try:
            idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx >= len(self.pts_map):
                    log.warning("frame %d beyond PTS map (%d) — stopping", idx, len(self.pts_map))
                    break
                yield idx, self.pts_map[idx], frame
                idx += 1
        finally:
            cap.release()


class Tracker(Protocol):
    def track(self, source: FrameSource) -> Iterator[tuple[int, float, list[Detection]]]:
        """Yield (frame_idx, t_s, detections-with-track-ids) per frame."""
        ...


class YoloTracker:
    def __init__(
        self,
        weights: str = "yolov8n.pt",
        tracker_cfg: str = "bytetrack.yaml",
        conf: float = 0.3,
        device: str = "cpu",
    ):
        from ultralytics import YOLO  # deferred: heavy import

        self.model = YOLO(weights)
        self.tracker_cfg = tracker_cfg
        self.conf = conf
        self.device = device
        self.class_ids = list(COCO_ROAD_USERS.keys())

    def track(self, source: FrameSource) -> Iterator[tuple[int, float, list[Detection]]]:
        for frame_idx, t_s, frame in source:
            results = self.model.track(
                frame,
                persist=True,
                tracker=self.tracker_cfg,
                conf=self.conf,
                classes=self.class_ids,
                device=self.device,
                verbose=False,
            )
            dets: list[Detection] = []
            boxes = results[0].boxes
            if boxes is not None and boxes.id is not None:
                for box, tid, cls_id, cf in zip(
                    boxes.xyxy.cpu().numpy(),
                    boxes.id.cpu().numpy().astype(int),
                    boxes.cls.cpu().numpy().astype(int),
                    boxes.conf.cpu().numpy(),
                ):
                    cls_name = COCO_ROAD_USERS.get(int(cls_id))
                    if cls_name is None:
                        continue
                    dets.append(Detection(
                        frame_idx=frame_idx, t_s=t_s, cls=cls_name, conf=float(cf),
                        x1_px=float(box[0]), y1_px=float(box[1]),
                        x2_px=float(box[2]), y2_px=float(box[3]),
                        track_id=int(tid),
                    ))
            yield frame_idx, t_s, dets


class FakeTracker:
    """Replays a detections script: {frame_idx: [detection dicts]}.
    Used by synthetic tests to exercise the pipeline downstream of the model."""

    def __init__(self, script_path: str | Path):
        raw = json.loads(Path(script_path).read_text())
        self.script: dict[int, list[dict]] = {int(k): v for k, v in raw.items()}

    def track(self, source: FrameSource) -> Iterator[tuple[int, float, list[Detection]]]:
        for frame_idx, t_s, _frame in source:
            dets = [
                Detection(
                    frame_idx=frame_idx, t_s=t_s, cls=d["cls"], conf=d.get("conf", 0.9),
                    x1_px=d["x1"], y1_px=d["y1"], x2_px=d["x2"], y2_px=d["y2"],
                    track_id=d["track_id"],
                )
                for d in self.script.get(frame_idx, [])
            ]
            yield frame_idx, t_s, dets
