"""API tests — run the pipeline into a temp dir, serve it, check the contract."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.run import run  # noqa: E402

SAMPLE = ROOT / "sample_data"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    if not (SAMPLE / "synthetic_intersection.mp4").exists():
        subprocess.check_call([sys.executable, str(ROOT / "scripts/make_synthetic_video.py")])
    runs_dir = tmp_path_factory.mktemp("runs")
    run(
        video=SAMPLE / "synthetic_intersection.mp4",
        thresholds_path=ROOT / "configs/thresholds/experimental_v1.yaml",
        tracker_kind="fake",
        script=SAMPLE / "synthetic_detections.json",
        weights="",
        out_root=runs_dir,
        camera_path=ROOT / "configs/cameras/synthetic_cam.yaml",
    )
    import os
    os.environ["SAFEROAD_RUNS_DIR"] = str(runs_dir)
    # import AFTER env var so the app picks up the temp dir
    import importlib
    import apps.api.main as api_main
    importlib.reload(api_main)
    from fastapi.testclient import TestClient
    return TestClient(api_main.app)


def test_list_runs(client):
    runs = client.get("/api/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "ok"


def test_summary_contract(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    s = client.get(f"/api/runs/{run_id}/summary").json()
    assert s["video"]["accepted"] is True
    assert s["tracking"]["total_road_users"] >= 3
    assert s["conflicts"]["events_total"] == 1
    assert s["conflicts"]["events_by_severity"].get("high", 0) + \
           s["conflicts"]["events_by_severity"].get("critical", 0) == 1
    assert "EXPERIMENTAL" in s["disclaimer"]
    assert s["calibration"]["reprojection_error_max_m"] < 0.01


def test_events_have_clip_urls(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    events = client.get(f"/api/runs/{run_id}/events").json()
    assert len(events) == 1
    ev = events[0]
    assert ev["clip_url"], "event must expose its evidence clip"
    clip = client.get(ev["clip_url"])
    assert clip.status_code == 200
    assert clip.headers["content-type"] == "video/mp4"
    assert len(clip.content) > 10_000


def test_annotated_video_served(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    r = client.get(f"/media/{run_id}/annotated.mp4")
    assert r.status_code == 200 and len(r.content) > 100_000


def test_unknown_run_404(client):
    assert client.get("/api/runs/nope/summary").status_code == 404


def test_path_traversal_blocked(client):
    run_id = client.get("/api/runs").json()[0]["run_id"]
    assert client.get(f"/media/{run_id}/clips/..%2F..%2Fmanifest.json").status_code == 404


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "SafeRoad AI" in r.text
