"""Unit tests for the track quality gate — synthetic tracks with known verdicts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.types import Detection
from vision.track_quality import GateConfig, apply_gate, find_teleports, split_on_gaps
from core.types import Track, TrackPoint


def make_frames(tracks: dict[int, list[tuple[float, float, float, str]]]):
    """tracks: {tid: [(t_s, x, y, cls)]}, boxes are 50x50 at (x, y)."""
    by_time: dict[float, list[Detection]] = {}
    for tid, pts in tracks.items():
        for i, (t, x, y, cls) in enumerate(pts):
            by_time.setdefault(t, []).append(Detection(
                frame_idx=int(round(t * 25)), t_s=t, cls=cls, conf=0.9,
                x1_px=x, y1_px=y, x2_px=x + 50, y2_px=y + 50, track_id=tid,
            ))
    frames = []
    for t in sorted(by_time):
        frames.append((int(round(t * 25)), t, by_time[t]))
    return frames


def steady(tid, cls="car", n=30, dt=0.04, speed_px_s=100.0):
    return {tid: [(i * dt, 100 + speed_px_s * i * dt, 200, cls) for i in range(n)]}


def test_clean_track_passes():
    frames = make_frames(steady(1))
    passed, quarantined, health = apply_gate(frames, GateConfig())
    assert len(passed) == 1 and not quarantined
    assert health.n_teleports == 0


def test_short_track_quarantined():
    frames = make_frames(steady(1, n=5))  # 0.2s only
    passed, quarantined, _ = apply_gate(frames, GateConfig())
    assert not passed and len(quarantined) == 1
    assert any("too_short" in f for f in quarantined[0].quality_flags)


def test_gap_splits_track():
    pts = [(i * 0.04, 100 + 4 * i, 200, "car") for i in range(30)]
    pts += [(2.0 + i * 0.04, 300 + 4 * i, 200, "car") for i in range(30)]  # 0.8s gap
    passed, quarantined, health = apply_gate(make_frames({7: pts}), GateConfig())
    assert health.n_gap_splits == 1
    assert len(passed) == 2  # two clean segments, same track_id, segments 0 and 1
    assert {t.segment for t in passed} == {0, 1}


def test_teleport_quarantined():
    pts = [(i * 0.04, 100 + 4 * i, 200, "car") for i in range(15)]
    pts += [(0.6 + i * 0.04, 900 + 4 * i, 600, "car") for i in range(15)]  # jump 800px
    passed, quarantined, health = apply_gate(make_frames({9: pts}), GateConfig())
    assert not passed and len(quarantined) == 1
    assert health.n_teleports >= 1
    assert any("teleport" in f for f in quarantined[0].quality_flags)


def test_no_silent_interpolation_through_gap():
    tr = Track(track_id=1, segment=0, cls="car", points=[
        TrackPoint(0, 0.0, 0, 0, 50, 50, 0.9),
        TrackPoint(50, 2.0, 500, 0, 550, 50, 0.9),
    ])
    segs = split_on_gaps(1, "car", tr.points, max_gap_s=0.5)
    assert len(segs) == 2  # the 2s hole must cut, never bridge


def test_teleport_scales_with_time_step():
    # a 300px move inside ONE 0.04s step is a teleport; the same total travel
    # spread over many small steps is not
    pts = []
    x = 100.0
    for i in range(20):
        if i == 10:
            x += 300  # sudden jump
        else:
            x += 4
        pts.append(TrackPoint(i, i * 0.04, x, 200, x + 50, 250, 0.9))
    fast = Track(track_id=1, segment=0, cls="car", points=pts)
    assert find_teleports(fast, GateConfig())
