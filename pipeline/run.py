"""Staged pipeline runner (tech plan v2 §10).

Every run creates output/runs/<run_id>/ with per-stage serialized artifacts:

    manifest.json        code versions, configs, video hash
    00_ingest/           ingest_report.json, pts_map.json
    01_tracks_raw/       raw tracker output (jsonl per frame)
    03_tracks_gated/     tracks.json + quarantine/quarantine.json + health.json
    08_evidence/         annotated.mp4

(Stage numbers reserve slots for calibration/motion/conflicts — Milestones 2-5.)

Usage:
    python -m pipeline.run --video sample_data/clip.mp4 \
        --thresholds configs/thresholds/experimental_v1.yaml
    python -m pipeline.run --video ... --tracker fake --script dets.json  # synthetic
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.log import get_logger                          # noqa: E402
from ingest.normalize import analyze, build_pts_map      # noqa: E402
from vision.detector import FakeTracker, FrameSource, YoloTracker  # noqa: E402
from vision.renderer import render                       # noqa: E402
from vision.track_quality import GateConfig, apply_gate  # noqa: E402

log = get_logger("pipeline")


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def run(video: Path, thresholds_path: Path, tracker_kind: str, script: Path | None,
        weights: str, out_root: Path, allow_rejected: bool = False) -> Path:
    t_start = time.time()
    thresholds = yaml.safe_load(thresholds_path.read_text()) if thresholds_path.exists() else {}
    gate_cfg = GateConfig.from_dict(thresholds.get("track_quality", {}))

    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + hashlib.sha256(
        video.read_bytes()[:1 << 20]).hexdigest()[:8]
    run_dir = out_root / run_id
    for sub in ["00_ingest", "01_tracks_raw", "03_tracks_gated/quarantine", "08_evidence"]:
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    # ---- stage 00: ingest & qualification -------------------------------
    report = analyze(video)
    report.to_json(run_dir / "00_ingest" / "ingest_report.json")
    if not report.accepted and not allow_rejected:
        log.error("stopping: video rejected by ingest (%s). "
                  "Use --allow-rejected to force (results will be untrustworthy).",
                  report.reject_reasons)
        _write_manifest(run_dir, video, thresholds_path, tracker_kind, weights,
                        status="rejected_at_ingest", elapsed_s=time.time() - t_start)
        return run_dir

    pts_map = build_pts_map(video)
    (run_dir / "00_ingest" / "pts_map.json").write_text(json.dumps(
        [round(t, 6) for t in pts_map]))

    # ---- stage 01: detection + tracking ---------------------------------
    if tracker_kind == "yolo":
        tracker = YoloTracker(weights=weights)
    elif tracker_kind == "fake":
        if script is None:
            raise SystemExit("--tracker fake requires --script detections.json")
        tracker = FakeTracker(script)
    else:
        raise SystemExit(f"unknown tracker: {tracker_kind}")

    frames = []
    raw_path = run_dir / "01_tracks_raw" / "frames.jsonl"
    with open(raw_path, "w") as f:
        for frame_idx, t_s, dets in tracker.track(FrameSource(video, pts_map)):
            frames.append((frame_idx, t_s, dets))
            f.write(json.dumps({
                "frame_idx": frame_idx, "t_s": round(t_s, 4),
                "detections": [d.to_dict() for d in dets],
            }) + "\n")
    log.info("tracking done: %d frames", len(frames))

    # ---- stage 03: quality gate -----------------------------------------
    passed, quarantined, health = apply_gate(frames, gate_cfg)
    (run_dir / "03_tracks_gated" / "tracks.json").write_text(json.dumps(
        [t.to_dict() for t in passed], indent=1))
    (run_dir / "03_tracks_gated" / "quarantine" / "quarantine.json").write_text(json.dumps(
        [t.to_dict() for t in quarantined], indent=1))
    (run_dir / "03_tracks_gated" / "health.json").write_text(json.dumps(
        health.to_dict(), indent=2))

    # ---- stage 08: annotated evidence -----------------------------------
    render(video, pts_map, passed, quarantined, run_dir / "08_evidence" / "annotated.mp4")

    _write_manifest(run_dir, video, thresholds_path, tracker_kind, weights,
                    status="ok", elapsed_s=time.time() - t_start)
    log.info("run complete: %s (%.1fs)", run_dir, time.time() - t_start)
    return run_dir


def _write_manifest(run_dir: Path, video: Path, thresholds_path: Path,
                    tracker_kind: str, weights: str, status: str, elapsed_s: float) -> None:
    (run_dir / "manifest.json").write_text(json.dumps({
        "status": status,
        "git_rev": _git_rev(),
        "python": platform.python_version(),
        "video": str(video),
        "thresholds_profile": str(thresholds_path),
        "tracker": tracker_kind,
        "weights": weights if tracker_kind == "yolo" else None,
        "elapsed_s": round(elapsed_s, 1),
    }, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="SafeRoad AI — Milestone 0+1 pipeline")
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--thresholds", type=Path,
                    default=ROOT / "configs/thresholds/experimental_v1.yaml")
    ap.add_argument("--tracker", choices=["yolo", "fake"], default="yolo")
    ap.add_argument("--script", type=Path, default=None,
                    help="detections script for --tracker fake")
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--out", type=Path, default=ROOT / "output/runs")
    ap.add_argument("--allow-rejected", action="store_true",
                    help="run even if ingest rejected the video (untrustworthy results)")
    args = ap.parse_args()
    run(args.video, args.thresholds, args.tracker, args.script,
        args.weights, args.out, args.allow_rejected)


if __name__ == "__main__":
    main()
