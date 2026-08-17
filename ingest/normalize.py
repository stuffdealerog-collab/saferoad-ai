"""Milestone 0 — ingest & qualification (tech plan v2 §3).

Real CCTV drops frames, uses variable frame rate (VFR) and lies in metadata.
Every downstream time-based metric (speed, TTC, PET) depends on a correct time
axis, so this module:

1. decodes the real presentation timestamp (PTS) of every frame via PyAV —
   we NEVER compute ``t = frame_idx / nominal_fps``;
2. detects VFR (spread of inter-frame intervals) and PTS gaps (dropped frames);
3. applies explicit rejection criteria and produces ``ingest_report.json``.

Rejection criteria (explicit, tech plan v2 §3):
- actual FPS < MIN_FPS (10);
- min(width, height) < MIN_RESOLUTION (720) in the analysis area;
- PTS unrecoverable;
- dropped-frame ratio > MAX_DROPPED_RATIO (5%).
"""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass, field, asdict
from pathlib import Path

import av

from core.log import get_logger

log = get_logger("ingest")

MIN_FPS = 10.0
MIN_RESOLUTION_PX = 720
MAX_DROPPED_RATIO = 0.05
# interval > GAP_FACTOR * median interval counts as a PTS gap (dropped frames)
GAP_FACTOR = 1.5
# coefficient of variation of intervals above this -> VFR
VFR_CV_THRESHOLD = 0.05


@dataclass
class IngestReport:
    video_path: str
    video_sha256: str
    width_px: int
    height_px: int
    codec: str
    nominal_fps: float | None       # what the container CLAIMS
    actual_fps_median: float | None  # what the PTS actually show
    n_frames: int
    duration_s: float
    interval_median_s: float | None
    interval_cv: float | None        # coefficient of variation of frame intervals
    is_vfr: bool
    n_gaps: int                      # intervals > GAP_FACTOR * median
    dropped_ratio: float             # estimated share of missing frames
    gap_positions_s: list[float] = field(default_factory=list)  # first 50 gap starts
    reject_reasons: list[str] = field(default_factory=list)
    accepted: bool = True

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(chunk):
            h.update(data)
    return h.hexdigest()


def extract_pts(video_path: Path) -> tuple[list[float], dict]:
    """Decode the video and return the real presentation time of every frame
    (seconds, monotonic) plus basic stream metadata.

    Raises ValueError if PTS are unrecoverable.
    """
    pts_s: list[float] = []
    with av.open(str(video_path)) as container:
        if not container.streams.video:
            raise ValueError("no video stream")
        stream = container.streams.video[0]
        meta = {
            "width": stream.codec_context.width,
            "height": stream.codec_context.height,
            "codec": stream.codec_context.name,
            "nominal_fps": float(stream.average_rate) if stream.average_rate else None,
        }
        tb = stream.time_base
        for frame in container.decode(stream):
            if frame.pts is None:
                # fall back to best-effort dts-derived time; count as degraded
                if frame.dts is None:
                    continue
                pts_s.append(float(frame.dts * tb))
            else:
                pts_s.append(float(frame.pts * tb))
    if len(pts_s) < 2:
        raise ValueError("PTS unrecoverable: fewer than 2 timestamped frames decoded")
    # PTS must be made monotonic (B-frame reorder is already handled by decode order,
    # but be defensive: sort and warn if reordering was needed)
    if any(b <= a for a, b in zip(pts_s, pts_s[1:])):
        log.warning("non-monotonic PTS after decode; sorting (%s)", video_path.name)
        pts_s = sorted(pts_s)
    # normalize to start at 0
    t0 = pts_s[0]
    return [t - t0 for t in pts_s], meta


def analyze(video_path: str | Path) -> IngestReport:
    """Qualify a video for analysis. Never raises on a *bad* video —
    a bad video produces accepted=False with explicit reasons.
    Raises only on unreadable input (that IS an analytical failure)."""
    video_path = Path(video_path)
    try:
        pts, meta = extract_pts(video_path)
        pts_ok = True
    except ValueError as e:
        log.error("PTS extraction failed for %s: %s", video_path, e)
        pts, meta, pts_ok = [], {"width": 0, "height": 0, "codec": "unknown", "nominal_fps": None}, False

    intervals = [b - a for a, b in zip(pts, pts[1:])] if len(pts) > 1 else []
    positive = [i for i in intervals if i > 0]

    if positive:
        med = statistics.median(positive)
        cv = (statistics.pstdev(positive) / med) if med > 0 else None
        actual_fps = 1.0 / med if med > 0 else None
        gaps = [(pts[i], iv) for i, iv in enumerate(intervals) if iv > GAP_FACTOR * med]
        # each gap of length iv hides approximately iv/med - 1 missing frames
        est_dropped = sum(max(iv / med - 1.0, 0.0) for _, iv in gaps)
        dropped_ratio = est_dropped / (len(pts) + est_dropped) if pts else 1.0
    else:
        med = cv = actual_fps = None
        gaps, dropped_ratio = [], 1.0

    reasons: list[str] = []
    if not pts_ok:
        reasons.append("pts_unrecoverable")
    if actual_fps is not None and actual_fps < MIN_FPS:
        reasons.append(f"fps_too_low: {actual_fps:.2f} < {MIN_FPS}")
    if min(meta["width"], meta["height"]) < MIN_RESOLUTION_PX and meta["width"] > 0:
        reasons.append(f"resolution_too_low: {meta['width']}x{meta['height']}")
    if dropped_ratio > MAX_DROPPED_RATIO:
        reasons.append(f"dropped_frames: {dropped_ratio:.1%} > {MAX_DROPPED_RATIO:.0%}")

    report = IngestReport(
        video_path=str(video_path),
        video_sha256=_sha256(video_path),
        width_px=meta["width"],
        height_px=meta["height"],
        codec=meta["codec"],
        nominal_fps=meta["nominal_fps"],
        actual_fps_median=round(actual_fps, 3) if actual_fps else None,
        n_frames=len(pts),
        duration_s=round(pts[-1], 3) if pts else 0.0,
        interval_median_s=round(med, 6) if med else None,
        interval_cv=round(cv, 4) if cv is not None else None,
        is_vfr=bool(cv is not None and cv > VFR_CV_THRESHOLD),
        n_gaps=len(gaps),
        dropped_ratio=round(dropped_ratio, 4),
        gap_positions_s=[round(t, 3) for t, _ in gaps[:50]],
        reject_reasons=reasons,
        accepted=not reasons,
    )
    if report.is_vfr:
        log.warning("VFR detected (cv=%.3f) — using per-frame PTS, not nominal fps", cv)
    if not report.accepted:
        log.error("video REJECTED: %s", "; ".join(reasons))
    else:
        log.info(
            "video accepted: %dx%d, %.2f fps actual (%.2f nominal), %d frames, %.1fs",
            report.width_px, report.height_px,
            report.actual_fps_median or 0, report.nominal_fps or 0,
            report.n_frames, report.duration_s,
        )
    return report


def build_pts_map(video_path: str | Path) -> list[float]:
    """frame_idx -> presentation time (s). The ONLY legal time source downstream."""
    pts, _ = extract_pts(Path(video_path))
    return pts
