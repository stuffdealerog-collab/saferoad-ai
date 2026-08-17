"""Staged pipeline runner (tech plan v2 §10).

Every run creates output/runs/<run_id>/ with per-stage serialized artifacts:

    manifest.json        code versions, configs, video hash
    00_ingest/           ingest_report.json, pts_map.json
    01_tracks_raw/       raw tracker output (jsonl per frame)
    03_tracks_gated/     tracks.json + quarantine/quarantine.json + health.json
    04_tracks_ground/    calibration_summary.json, tracks_ground.json  (needs camera calibration)
    05_tracks_smoothed/  states.json, braking.json                     (Kalman/RTS)
    06_conflicts/        pairs.json, occupancies.json, pet.json        (needs zones for PET)
    07_events/           events.json                                   (near-miss engine)
    08_evidence/         annotated.mp4

Stages 04-05 run only when the camera config has calibration; without it the
pipeline legally stops at image space — it never guesses meters from pixels.

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
from geometry.zones import load_zones                    # noqa: E402
from ingest.normalize import analyze, build_pts_map      # noqa: E402
from motion.state_estimation import detect_hard_braking, estimate_track  # noqa: E402
from safety.conflicts import TrackStates, analyze_all    # noqa: E402
from safety.nearmiss import build_events                 # noqa: E402
from vision.evidence import render_all_events            # noqa: E402
from vision.calibration import CameraCalibration         # noqa: E402
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
        weights: str, out_root: Path, allow_rejected: bool = False,
        camera_path: Path | None = None) -> Path:
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

    # ---- stages 04-05: ground plane + state estimation ------------------
    calibration = CameraCalibration.from_camera_yaml(camera_path) if camera_path else None
    if calibration is not None:
        g_dir = run_dir / "04_tracks_ground"
        s_dir = run_dir / "05_tracks_smoothed"
        g_dir.mkdir(exist_ok=True)
        s_dir.mkdir(exist_ok=True)
        g_dir.joinpath("calibration_summary.json").write_text(
            json.dumps(calibration.summary(), indent=2))

        ground_tracks, states_out, braking_out = [], [], []
        for tr in passed:
            gps = [calibration.project(p.bottom_center_px) for p in tr.points]
            ground_tracks.append({
                "track_id": tr.track_id, "segment": tr.segment, "cls": tr.cls,
                "points": [
                    {"t_s": round(p.t_s, 4), "x_m": round(g.x_m, 3), "y_m": round(g.y_m, 3),
                     "sigma_m": round(g.sigma_m, 3), "inside_validity_mask": g.inside_validity_mask}
                    for p, g in zip(tr.points, gps)
                ],
            })
            if len(tr.points) >= 3:
                states = estimate_track(
                    ts=[p.t_s for p in tr.points],
                    xs_m=[g.x_m for g in gps],
                    ys_m=[g.y_m for g in gps],
                    sigmas_m=[g.sigma_m for g in gps],
                    inside_mask=[g.inside_validity_mask for g in gps],
                )
                braking = detect_hard_braking(states)
                states_out.append({
                    "track_id": tr.track_id, "segment": tr.segment, "cls": tr.cls,
                    "states": [s.to_dict() for s in states],
                })
                if braking:
                    braking_out.append({
                        "track_id": tr.track_id, "segment": tr.segment, "cls": tr.cls,
                        "episodes": braking,
                    })
        g_dir.joinpath("tracks_ground.json").write_text(json.dumps(ground_tracks, indent=1))
        s_dir.joinpath("states.json").write_text(json.dumps(states_out, indent=1))
        s_dir.joinpath("braking.json").write_text(json.dumps(braking_out, indent=1))
        log.info("ground/motion stages done: %d tracks projected, %d braking episodes",
                 len(ground_tracks), sum(len(b["episodes"]) for b in braking_out))

        # ---- stage 06: conflict analysis --------------------------------
        c_dir = run_dir / "06_conflicts"
        c_dir.mkdir(exist_ok=True)
        zones = load_zones(camera_path)
        track_states = [TrackStates.from_states_dict(d) for d in states_out]
        frame_step = report.interval_median_s or 0.04
        pairs, occupancies, pets = analyze_all(track_states, zones, frame_step)
        c_dir.joinpath("pairs.json").write_text(json.dumps(
            [p.to_dict() for p in pairs], indent=1))
        c_dir.joinpath("occupancies.json").write_text(json.dumps(
            [o.to_dict() for o in occupancies], indent=1))
        c_dir.joinpath("pet.json").write_text(json.dumps(
            [p.__dict__ for p in pets], indent=1))

        # ---- stage 07: near-miss events ---------------------------------
        e_dir = run_dir / "07_events"
        e_dir.mkdir(exist_ok=True)
        profile_id = thresholds_path.stem
        events = build_events(
            pairs=[p.to_dict() for p in pairs],
            pets=[p.__dict__ for p in pets],
            braking=braking_out,
            rules=thresholds.get("nearmiss"),
            profile_id=profile_id,
        )
        e_dir.joinpath("events.json").write_text(json.dumps(
            [e.to_dict() for e in events], indent=1))
    else:
        log.info("no camera calibration — stages 04-07 skipped (image space only)")
        events, zones = [], []

    # ---- stage 08: annotated evidence -----------------------------------
    render(video, pts_map, passed, quarantined, run_dir / "08_evidence" / "annotated.mp4")
    if events:
        zones_by_id = {z.zone_id: z.polygon_m for z in zones}
        clip_manifest = render_all_events(
            video, pts_map, [e.to_dict() for e in events], passed,
            calibration, zones_by_id, run_dir / "08_evidence" / "clips")
        (run_dir / "08_evidence" / "clips" / "manifest.json").write_text(
            json.dumps(clip_manifest, indent=2))

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
    ap.add_argument("--camera", type=Path, default=None,
                    help="per-camera YAML with calibration (enables stages 04-05)")
    args = ap.parse_args()
    run(args.video, args.thresholds, args.tracker, args.script,
        args.weights, args.out, args.allow_rejected, camera_path=args.camera)


if __name__ == "__main__":
    main()
