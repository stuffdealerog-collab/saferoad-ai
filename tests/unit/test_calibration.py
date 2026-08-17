"""Unit tests for homography calibration — known transforms, analytic truth."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pytest

from vision.calibration import CameraCalibration


def scale_calibration(scale_px_per_m=20.0, mask=None):
    """Pure top-down: ground = (px - center) / scale."""
    img = np.array([[0, 0], [1280, 0], [1280, 720], [0, 720]], dtype=float)
    gnd = (img - np.array([640.0, 360.0])) / scale_px_per_m
    return CameraCalibration(img, gnd, mask, camera_id="test_topdown")


def test_topdown_roundtrip_exact():
    cal = scale_calibration()
    assert cal.reprojection_error_max_m < 1e-6
    g = cal.project((640.0, 360.0))
    assert abs(g.x_m) < 1e-6 and abs(g.y_m) < 1e-6
    g2 = cal.project((840.0, 360.0))  # 200 px right = 10 m
    assert abs(g2.x_m - 10.0) < 1e-6


def test_perspective_case_roundtrip():
    # a real oblique-view trapezoid: 4 image points of a 20x40 m road patch
    img = np.array([[400, 700], [880, 700], [700, 300], [560, 300]], dtype=float)
    gnd = np.array([[-10, 0], [10, 0], [10, 40], [-10, 40]], dtype=float)
    cal = CameraCalibration(img, gnd, None, camera_id="test_perspective")
    assert cal.reprojection_error_max_m < 1e-6  # 4 points define H exactly
    # far points must carry larger uncertainty than near points (Jacobian grows)
    near = cal.project((640.0, 690.0))
    far = cal.project((635.0, 310.0))
    assert far.sigma_m > near.sigma_m * 2


def test_validity_mask_flags_outside_points():
    mask = np.array([[100, 100], [1180, 100], [1180, 620], [100, 620]], dtype=float)
    cal = scale_calibration(mask=mask)
    assert cal.project((640.0, 360.0)).inside_validity_mask
    assert not cal.project((10.0, 10.0)).inside_validity_mask


def test_inconsistent_reference_points_reported():
    img = np.array([[0, 0], [1280, 0], [1280, 720], [0, 720], [640, 360]], dtype=float)
    gnd = (img - np.array([640.0, 360.0])) / 20.0
    gnd[4] = [5.0, 5.0]  # deliberately wrong 5th point -> nonzero residual
    cal = CameraCalibration(img, gnd, None, camera_id="test_bad")
    assert cal.reprojection_error_max_m > 0.5  # error is REPORTED, not hidden


def test_too_few_points_rejected():
    with pytest.raises(ValueError):
        CameraCalibration(np.zeros((3, 2)), np.zeros((3, 2)), None)
