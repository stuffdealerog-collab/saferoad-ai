"""Shared data types for the SafeRoad pipeline.

Conventions (tech plan v2, principle #11-13):
- all times are seconds (float) on the video's presentation-time axis, never frame_idx / nominal_fps;
- image coordinates are pixels (x right, y down); ground coordinates (Milestone 2) are meters;
- every quantity carries its unit in the field name (``_s``, ``_px``, ``_m``, ``_mps``).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

# COCO class ids -> SafeRoad road-user classes (tech plan v2 §detection)
COCO_ROAD_USERS = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
ROAD_USER_CLASSES = sorted(set(COCO_ROAD_USERS.values()))


@dataclass
class Detection:
    """A single detection in one frame (image space)."""
    frame_idx: int
    t_s: float                       # presentation time, seconds (from ingest PTS map)
    cls: str                         # one of ROAD_USER_CLASSES
    conf: float
    x1_px: float
    y1_px: float
    x2_px: float
    y2_px: float
    track_id: Optional[int] = None   # filled by the tracker

    @property
    def bottom_center_px(self) -> tuple[float, float]:
        """Assumed ground-contact point (tech plan v2 assumption #2)."""
        return ((self.x1_px + self.x2_px) / 2.0, self.y2_px)

    @property
    def diag_px(self) -> float:
        return ((self.x2_px - self.x1_px) ** 2 + (self.y2_px - self.y1_px) ** 2) ** 0.5

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrackPoint:
    frame_idx: int
    t_s: float
    x1_px: float
    y1_px: float
    x2_px: float
    y2_px: float
    conf: float

    @property
    def bottom_center_px(self) -> tuple[float, float]:
        return ((self.x1_px + self.x2_px) / 2.0, self.y2_px)

    @property
    def diag_px(self) -> float:
        return ((self.x2_px - self.x1_px) ** 2 + (self.y2_px - self.y1_px) ** 2) ** 0.5


@dataclass
class Track:
    """A persistent road user. ``track_id`` is stable across the whole video;
    ``segment`` disambiguates pieces after a gap split (gap > max_gap_s is cut,
    never silently interpolated — tech plan v2 §5)."""
    track_id: int
    segment: int
    cls: str
    points: list[TrackPoint] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)   # empty == passed the gate
    quarantined: bool = False

    @property
    def duration_s(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].t_s - self.points[0].t_s

    @property
    def n_points(self) -> int:
        return len(self.points)

    @property
    def mean_conf(self) -> float:
        if not self.points:
            return 0.0
        return sum(p.conf for p in self.points) / len(self.points)

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "segment": self.segment,
            "cls": self.cls,
            "duration_s": round(self.duration_s, 3),
            "n_points": self.n_points,
            "mean_conf": round(self.mean_conf, 3),
            "quarantined": self.quarantined,
            "quality_flags": self.quality_flags,
            "points": [
                {
                    "frame_idx": p.frame_idx,
                    "t_s": round(p.t_s, 4),
                    "bbox_px": [round(p.x1_px, 1), round(p.y1_px, 1), round(p.x2_px, 1), round(p.y2_px, 1)],
                    "conf": round(p.conf, 3),
                }
                for p in self.points
            ],
        }
