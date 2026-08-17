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
        camera_path=ROOT / "configs/cameras/synthetic_cam.yaml",
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


def test_ground_stage_artifacts_exist(synthetic_run):
    for rel in [
        "04_tracks_ground/calibration_summary.json",
        "04_tracks_ground/tracks_ground.json",
        "05_tracks_smoothed/states.json",
        "05_tracks_smoothed/braking.json",
    ]:
        assert (synthetic_run / rel).exists(), f"missing artifact: {rel}"
    summary = json.loads((synthetic_run / "04_tracks_ground/calibration_summary.json").read_text())
    assert summary["reprojection_error_max_m"] < 0.01  # synthetic cal is exact


def test_car1_speed_recovered_in_kmh(synthetic_run):
    """car1 moves 120 px/s; synthetic calibration is 20 px/m -> 6.0 m/s = 21.6 km/h."""
    states = json.loads((synthetic_run / "05_tracks_smoothed/states.json").read_text())
    car1 = next(s for s in states if s["track_id"] == 1)
    mid = car1["states"][15:-15]
    mean_speed = sum(s["speed_mps"] for s in mid) / len(mid)
    assert abs(mean_speed - 6.0) / 6.0 < 0.05, f"expected ~6 m/s, got {mean_speed:.2f}"
    for s in mid:
        assert s["speed_sigma_mps"] > 0  # uncertainty must be populated, never 0


def test_no_phantom_braking_on_synthetic_constant_speeds(synthetic_run):
    """Every synthetic actor moves at constant speed -> braking.json must be empty."""
    braking = json.loads((synthetic_run / "05_tracks_smoothed/braking.json").read_text())
    assert braking == [], f"phantom braking episodes: {braking}"


def test_conflict_stage_artifacts_exist(synthetic_run):
    for rel in ["06_conflicts/pairs.json", "06_conflicts/occupancies.json",
                "06_conflicts/pet.json"]:
        assert (synthetic_run / rel).exists(), f"missing artifact: {rel}"


def test_pedestrian_car_pet_matches_analytic_truth(synthetic_run):
    """Analytic truth of the synthetic scene (20 px/m, zebra zone x[-8.5,-3.9]):
    person3 exits the zebra zone at t=4.0s (bottom-center y=435px);
    car1 enters it at t=4.375s (bottom-center x=470px) -> PET = 0.375s."""
    pets = json.loads((synthetic_run / "06_conflicts/pet.json").read_text())
    zebra = [p for p in pets if p["applicable"] and p["zone_id"] == "zebra_west"
             and {p["first"]["track_id"], p["second"]["track_id"]} == {1, 3}]
    assert zebra, "person3->car1 PET through zebra_west must exist"
    pet = zebra[0]["pet_s"]
    assert abs(pet - 0.375) < 0.12, f"expected PET ~0.375s, got {pet}"  # +- ~3 frames


def test_occlusion_truncated_occupancy_never_produces_pet(synthetic_run):
    """car2 disappears at t=5.0s while inside intersection_core -> its exit is
    unobserved; every PET involving that occupancy as 'first' must be refused."""
    occs = json.loads((synthetic_run / "06_conflicts/occupancies.json").read_text())
    trunc = [o for o in occs if o["track_id"] == 2 and o["zone_id"] == "intersection_core"
             and not o["exit_observed"]]
    assert trunc, "car2 segment-0 must have an exit-unobserved occupancy in the core"

    pets = json.loads((synthetic_run / "06_conflicts/pet.json").read_text())
    for p in pets:
        if p["applicable"] and p["first"]["track_id"] == 2 and \
                p["zone_id"] == "intersection_core" and not p["first"]["exit_observed"]:
            raise AssertionError(f"fake PET from truncated occupancy: {p}")


def test_car_pedestrian_min_separation_reasonable(synthetic_run):
    """Analytic: closest approach car1<->person3 is ~5.2m at t~4.5s."""
    pairs = json.loads((synthetic_run / "06_conflicts/pairs.json").read_text())
    cp = [p for p in pairs if p["analyzable"] and
          {p["track_a"]["track_id"], p["track_b"]["track_id"]} == {1, 3}]
    assert cp, "car1-person3 pair must be analyzable"
    p = cp[0]
    assert abs(p["min_separation_m"] - 5.2) < 0.6, p["min_separation_m"]
    assert p["conflict_angle_class"] == "pedestrian"
    assert 4.0 < p["t_min_separation_s"] < 5.0


def test_crossing_cars_classified_as_crossing(synthetic_run):
    """car1 (east) vs car2 (south): heading difference ~90 deg -> crossing."""
    pairs = json.loads((synthetic_run / "06_conflicts/pairs.json").read_text())
    cc = [p for p in pairs if p["analyzable"] and
          {p["track_a"]["track_id"], p["track_b"]["track_id"]} == {1, 2}]
    assert cc
    assert any(p["conflict_angle_class"] == "crossing" for p in cc)


def test_exactly_one_nearmiss_event_the_zebra_case(synthetic_run):
    """The whole point of the MVP in one assertion: the synthetic scene contains
    exactly ONE near-miss-grade situation (person3 vs car1, PET 0.375s on the
    zebra) — the engine must find it and nothing else."""
    events = json.loads((synthetic_run / "07_events/events.json").read_text())
    assert len(events) == 1, f"expected exactly 1 event, got {len(events)}: " + \
        str([(e['road_user_a']['track_id'], e['road_user_b']['track_id'],
              e['reason_codes']) for e in events])
    ev = events[0]
    assert {ev["road_user_a"]["track_id"], ev["road_user_b"]["track_id"]} == {1, 3}
    assert "low_pet" in ev["reason_codes"]
    assert "pedestrian_involved" in ev["reason_codes"]
    assert ev["severity"] in ("high", "critical")
    assert ev["zone_id"] == "zebra_west"
    assert ev["thresholds_profile_id"] == "experimental_v1"
    assert ev["metrics"]["pet_s"] is not None
    # the event window must cover the actual conflict moment (~t=4.0-4.4s)
    assert ev["t_start_s"] < 4.0 < ev["t_end_s"] or ev["t_start_s"] < 4.4 < ev["t_end_s"]


def test_evidence_clip_rendered_for_event(synthetic_run):
    manifest_p = synthetic_run / "08_evidence/clips/manifest.json"
    assert manifest_p.exists()
    manifest = json.loads(manifest_p.read_text())
    events = json.loads((synthetic_run / "07_events/events.json").read_text())
    assert len(manifest) == len(events) == 1
    clip = synthetic_run / "08_evidence/clips" / manifest[0]["clip"]
    assert clip.exists() and clip.stat().st_size > 10_000
    # browsers only play H.264 — mp4v would show a black rectangle on the demo
    import av
    with av.open(str(clip)) as c:
        assert c.streams.video[0].codec_context.name == "h264", \
            "evidence clip must be H.264 for browser playback"
    with av.open(str(synthetic_run / "08_evidence/annotated.mp4")) as c:
        assert c.streams.video[0].codec_context.name == "h264"
    import cv2
    cap = cv2.VideoCapture(str(clip))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    # event window ~[3.0..5.4]s + 2*0.5s pad at 25fps -> at least 60 frames
    assert n >= 60, f"clip too short: {n} frames"


def test_timestamps_come_from_pts_not_frame_math(synthetic_run):
    pts_map = json.loads((synthetic_run / "00_ingest/pts_map.json").read_text())
    assert all(b > a for a, b in zip(pts_map, pts_map[1:])), "PTS must be monotonic"
    tracks = json.loads((synthetic_run / "03_tracks_gated/tracks.json").read_text())
    for t in tracks:
        for p in t["points"]:
            assert 0 <= p["t_s"] <= pts_map[-1] + 1e-6
