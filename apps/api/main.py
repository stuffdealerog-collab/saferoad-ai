"""Milestone 7 — SafeRoad AI dashboard API.

Serves analysis runs (the staged artifacts of pipeline/run.py) plus the
single-page dashboard. One command:

    python -m uvicorn apps.api.main:app --port 8000

Tech plan note: the long-term web stack is Next.js/TypeScript (v2 §12); this
MVP dashboard is deliberately a zero-build static page served by the API so a
demo needs one process and no node toolchain. The API surface is already the
one the Next.js app will consume later.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import os

RUNS_DIR = Path(os.environ.get("SAFEROAD_RUNS_DIR", ROOT / "output" / "runs"))
WEB_DIR = ROOT / "apps" / "web"

app = FastAPI(title="SafeRoad AI", version="0.1.0-mvp")


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _run_dir(run_id: str) -> Path:
    d = RUNS_DIR / run_id
    if not d.is_dir() or ".." in run_id or "/" in run_id:
        raise HTTPException(404, f"run not found: {run_id}")
    return d


@app.get("/api/runs")
def list_runs() -> list[dict]:
    runs = []
    if RUNS_DIR.is_dir():
        for d in sorted(RUNS_DIR.iterdir(), reverse=True):
            manifest = _read_json(d / "manifest.json")
            if manifest:
                runs.append({"run_id": d.name, **manifest})
    return runs


@app.get("/api/runs/{run_id}/summary")
def run_summary(run_id: str) -> dict:
    d = _run_dir(run_id)
    ingest = _read_json(d / "00_ingest" / "ingest_report.json", {})
    health = _read_json(d / "03_tracks_gated" / "health.json", {})
    tracks = _read_json(d / "03_tracks_gated" / "tracks.json", [])
    events = _read_json(d / "07_events" / "events.json", [])
    pairs = _read_json(d / "06_conflicts" / "pairs.json", [])
    calibration = _read_json(d / "04_tracks_ground" / "calibration_summary.json")

    by_class: dict[str, int] = {}
    for t in tracks:
        by_class[t["cls"]] = by_class.get(t["cls"], 0) + 1
    by_severity: dict[str, int] = {}
    for e in events:
        by_severity[e["severity"]] = by_severity.get(e["severity"], 0) + 1

    return {
        "run_id": run_id,
        "manifest": _read_json(d / "manifest.json", {}),
        "video": {
            "duration_s": ingest.get("duration_s"),
            "actual_fps": ingest.get("actual_fps_median"),
            "resolution": [ingest.get("width_px"), ingest.get("height_px")],
            "accepted": ingest.get("accepted"),
            "reject_reasons": ingest.get("reject_reasons", []),
            "is_vfr": ingest.get("is_vfr"),
        },
        "tracking": {
            "road_users_by_class": by_class,
            "total_road_users": len({(t["track_id"]) for t in tracks}),
            "health": health,
        },
        "calibration": calibration,
        "conflicts": {
            "pairs_analyzed": sum(1 for p in pairs if p.get("analyzable")),
            "events_total": len(events),
            "events_by_severity": by_severity,
        },
        "disclaimer": "Risk metrics use EXPERIMENTAL thresholds "
                      "(profile: %s); scores are prioritization indices, "
                      "not accident probabilities."
                      % (events[0]["thresholds_profile_id"] if events else "n/a"),
    }


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str) -> list[dict]:
    d = _run_dir(run_id)
    events = _read_json(d / "07_events" / "events.json", [])
    clips = {c["event_id"]: c["clip"]
             for c in _read_json(d / "08_evidence" / "clips" / "manifest.json", [])}
    for e in events:
        e["clip_url"] = (f"/media/{run_id}/clips/{clips[e['event_id']]}"
                         if e["event_id"] in clips else None)
    return events


@app.get("/api/runs/{run_id}/braking")
def run_braking(run_id: str) -> list[dict]:
    return _read_json(_run_dir(run_id) / "05_tracks_smoothed" / "braking.json", [])


@app.get("/media/{run_id}/annotated.mp4")
def media_annotated(run_id: str):
    p = _run_dir(run_id) / "08_evidence" / "annotated.mp4"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.get("/media/{run_id}/clips/{name}")
def media_clip(run_id: str, name: str):
    if "/" in name or ".." in name:
        raise HTTPException(404)
    p = _run_dir(run_id) / "08_evidence" / "clips" / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4")


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB_DIR / "index.html").read_text()
