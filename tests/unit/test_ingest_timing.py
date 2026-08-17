"""Unit tests for ingest timing analysis — synthetic PTS arrays with known truth."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import statistics

from ingest.normalize import GAP_FACTOR, VFR_CV_THRESHOLD


def intervals_stats(pts):
    intervals = [b - a for a, b in zip(pts, pts[1:])]
    med = statistics.median(intervals)
    cv = statistics.pstdev(intervals) / med
    gaps = [iv for iv in intervals if iv > GAP_FACTOR * med]
    return med, cv, gaps


def test_cfr_stream_has_low_cv_and_no_gaps():
    pts = [i / 25.0 for i in range(250)]  # perfect 25 fps
    med, cv, gaps = intervals_stats(pts)
    assert abs(med - 0.04) < 1e-9
    assert cv < VFR_CV_THRESHOLD
    assert not gaps


def test_dropped_frames_detected_as_gaps():
    # 25 fps with every 10th frame missing -> gap of 2*0.04 every 10 frames
    pts = [i / 25.0 for i in range(250) if i % 10 != 5]
    med, cv, gaps = intervals_stats(pts)
    assert abs(med - 0.04) < 1e-9
    assert len(gaps) == 25  # one gap per removed frame


def test_vfr_stream_detected():
    # alternating 30/15 fps intervals -> high CV
    pts, t = [0.0], 0.0
    for i in range(200):
        t += 1 / 30.0 if i % 2 == 0 else 1 / 15.0
        pts.append(t)
    _, cv, _ = intervals_stats(pts)
    assert cv > VFR_CV_THRESHOLD
