"""End-to-end pipeline test on the synthetic intersection (known ground truth).

Generates the synthetic video if missing, runs the full staged pipeline with
FakeTracker, and checks the gate verdicts against synthetic_truth.json.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.run import run  # noqa: E402

SAMPLE = ROOT / "sample_data"
VIDEO = SAMPLE / "synthetic_intersection.mp4"
SCRIPT = SAMPLE / "synthetic_detections.json"
TRUTH = SAMPLE / "synthetic_truth.json"


@pytest.fixture(scope="module")
def synthetic_run(tmp_path_factory):
    if not VIDEO.exists() or not SCRIPT.exists():
        subprocess.check_call([sys.executable, str(ROOT / "scripts/make_synthetic_video.py")])
    out = tmp_path_factory.mktemp("runs")
    run_dir = run(
        video=VIDEO,
        thresholds_path=ROOT / "configs/thresholds/experimental_v1.yaml",
        tracker_kind="fake",
        script=SCRIPT,
        weights="",
        out_root=out,
    )
    return run_dir


def test_artifacts_exist(synthetic_run):
    for rel in [
        "manifest.json",
        "00_ingest/ingest_report.json",
        "00_ingest/pts_map.json",
        "01_tracks_raw/frames.jsonl",
        "03_tracks_gated/tracks.json",
        "03_tracks_gated/quarantine/quarantine.json",
        "03_tracks_gated/health.json",
        "08_evidence/annotated.mp4",
    ]:
        assert (synthetic_run / rel).exists(), f"missing artifact: {rel}"


def test_ingest_accepts_synthetic_video(synthetic_run):
    report = json.loads((synthetic_run / "00_ingest/ingest_report.json").read_text())
    assert report["accepted"], report["reject_reasons"]
    assert abs(report["actual_fps_median"] - 25.0) < 1.0
    assert not report["is_vfr"]


def test_gate_verdicts_match_truth(synthetic_run):
    truth = json.loads(TRUTH.read_text())
    tracks = json.loads((synthetic_run / "03_tracks_gated/tracks.json").read_text())
    quarantine = json.loads(
        (synthetic_run / "03_tracks_gated/quarantine/quarantine.json").read_text())

    passed_ids = {t["track_id"] for t in tracks}
    quarantined_ids = {t["track_id"] for t in quarantine}

    for tid in truth["expected_passed_track_ids"]:
        assert tid in passed_ids, f"track {tid} should pass the gate"
    for tid in truth["expected_quarantined_track_ids"]:
        assert tid in quarantined_ids, f"track {tid} (teleporter) must be quarantined"
        assert tid not in passed_ids
    for tid in truth["expected_too_short_track_ids"]:
        assert tid not in passed_ids, f"track {tid} (flicker) must not pass"

    # occluded car must be split into exactly 2 passed segments
    gap_tid = truth["expected_gap_split_track_id"]
    segments = [t for t in tracks if t["track_id"] == gap_tid]
    assert len(segments) == 2, f"track {gap_tid} must be split by the 1s occlusion"


def test_timestamps_come_from_pts_not_frame_math(synthetic_run):
    pts_map = json.loads((synthetic_run / "00_ingest/pts_map.json").read_text())
    assert all(b > a for a, b in zip(pts_map, pts_map[1:])), "PTS must be monotonic"
    tracks = json.loads((synthetic_run / "03_tracks_gated/tracks.json").read_text())
    for t in tracks:
        for p in t["points"]:
            assert 0 <= p["t_s"] <= pts_map[-1] + 1e-6
