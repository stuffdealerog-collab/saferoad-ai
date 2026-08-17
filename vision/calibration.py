"""Milestone 2 — camera calibration via manual homography (tech plan v2 §4, §6).

Explicit assumptions (never silent):
- the ground in the analysis area is a PLANE (``ground_plane_assumption: flat``);
- the object's ground-contact point is the bbox bottom-center (degrades under
  partial occlusion and two-wheeler lean — tech plan v2 assumption #2);
- calibration error is only bounded INSIDE the validity mask; points outside
  are flagged and excluded from metric computation, not silently trusted.

The homography is computed from >= 4 image<->ground reference point pairs.
Reprojection error is computed on the reference points themselves and stored
in every analysis report; it is a lower bound of the real error, not proof of
accuracy (real validation = GPS probe run, Milestone 8).

Uncertainty: the Jacobian of the image->ground mapping scales a nominal
per-detection pixel noise into meters, so far-away points carry honestly
larger sigma (tech plan v2 §6: measurement noise grows with distance).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml

from core.log import get_logger

log = get_logger("vision.calibration")

# nominal detector localization noise in pixels (bbox bottom-center jitter)
NOMINAL_PIXEL_SIGMA_PX = 3.0


@dataclass
class GroundPoint:
    x_m: float
    y_m: float
    sigma_m: float           # 1-sigma positional uncertainty, meters
    inside_validity_mask: bool


class CameraCalibration:
    def __init__(
        self,
        image_points: np.ndarray,      # (N,2) px
        ground_points: np.ndarray,     # (N,2) m
        validity_mask_px: np.ndarray | None,  # (M,2) polygon in image coords, or None
        camera_id: str = "unknown",
    ):
        if len(image_points) < 4:
            raise ValueError("homography needs >= 4 reference points")
        if len(image_points) != len(ground_points):
            raise ValueError("image/ground reference point count mismatch")

        self.camera_id = camera_id
        self.image_points = np.asarray(image_points, dtype=np.float64)
        self.ground_points = np.asarray(ground_points, dtype=np.float64)
        self.validity_mask_px = (
            np.asarray(validity_mask_px, dtype=np.float32) if validity_mask_px is not None else None
        )

        H, _ = cv2.findHomography(self.image_points, self.ground_points, method=0)
        if H is None:
            raise ValueError("homography estimation failed (degenerate reference points?)")
        self.H = H

        # reprojection error on the reference points (image -> ground)
        proj = self.image_to_ground_batch(self.image_points)
        err = np.linalg.norm(proj - self.ground_points, axis=1)
        self.reprojection_error_mean_m = float(err.mean())
        self.reprojection_error_max_m = float(err.max())
        log.info(
            "calibration[%s]: %d ref points, reprojection error mean=%.3fm max=%.3fm",
            camera_id, len(self.image_points),
            self.reprojection_error_mean_m, self.reprojection_error_max_m,
        )
        if self.reprojection_error_max_m > 0.5:
            log.warning(
                "calibration[%s]: max reprojection error %.2fm > 0.5m — "
                "reference points are likely inconsistent; speeds will be untrustworthy",
                camera_id, self.reprojection_error_max_m,
            )

    # ---------------- transforms ----------------

    def image_to_ground_batch(self, pts_px: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts_px, dtype=np.float64).reshape(-1, 1, 2)
        out = cv2.perspectiveTransform(pts, self.H)
        return out.reshape(-1, 2)

    def jacobian_scale_m_per_px(self, pt_px: tuple[float, float]) -> float:
        """Local linear scale of the mapping at pt (max singular value of the
        Jacobian): how many meters one pixel of error becomes HERE."""
        x, y = float(pt_px[0]), float(pt_px[1])
        h = self.H
        w = h[2, 0] * x + h[2, 1] * y + h[2, 2]
        gx = h[0, 0] * x + h[0, 1] * y + h[0, 2]
        gy = h[1, 0] * x + h[1, 1] * y + h[1, 2]
        # d(gx/w)/dx etc. via quotient rule
        J = np.array([
            [(h[0, 0] * w - gx * h[2, 0]) / w**2, (h[0, 1] * w - gx * h[2, 1]) / w**2],
            [(h[1, 0] * w - gy * h[2, 0]) / w**2, (h[1, 1] * w - gy * h[2, 1]) / w**2],
        ])
        return float(np.linalg.svd(J, compute_uv=False)[0])

    def in_validity_mask(self, pt_px: tuple[float, float]) -> bool:
        if self.validity_mask_px is None:
            return True   # no mask configured -> whole frame (explicitly weaker setup)
        return cv2.pointPolygonTest(
            self.validity_mask_px.reshape(-1, 1, 2), (float(pt_px[0]), float(pt_px[1])), False
        ) >= 0

    def project(self, pt_px: tuple[float, float]) -> GroundPoint:
        g = self.image_to_ground_batch(np.array([pt_px]))[0]
        scale = self.jacobian_scale_m_per_px(pt_px)
        sigma = NOMINAL_PIXEL_SIGMA_PX * scale + self.reprojection_error_mean_m
        return GroundPoint(
            x_m=float(g[0]), y_m=float(g[1]),
            sigma_m=float(sigma),
            inside_validity_mask=self.in_validity_mask(pt_px),
        )

    # ---------------- config I/O ----------------

    @classmethod
    def from_camera_yaml(cls, path: str | Path) -> "CameraCalibration | None":
        """Returns None (with a log line) if the camera has no calibration yet —
        the pipeline then legally skips ground-plane stages, it does NOT guess."""
        cfg = yaml.safe_load(Path(path).read_text())
        cal = cfg.get("calibration", {}) or {}
        img_pts = cal.get("image_points") or []
        gnd_pts = cal.get("ground_points_m") or []
        if len(img_pts) < 4:
            log.warning("camera %s has no calibration (image_points < 4) — "
                        "ground-plane stages will be skipped", cfg.get("camera_id"))
            return None
        assumption = cal.get("ground_plane_assumption", "flat")
        if assumption != "flat":
            raise ValueError(f"unsupported ground_plane_assumption: {assumption}")
        mask = cal.get("validity_mask")
        return cls(
            image_points=np.array(img_pts, dtype=np.float64),
            ground_points=np.array(gnd_pts, dtype=np.float64),
            validity_mask_px=np.array(mask, dtype=np.float32) if mask else None,
            camera_id=cfg.get("camera_id", "unknown"),
        )

    def summary(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "n_reference_points": int(len(self.image_points)),
            "reprojection_error_mean_m": round(self.reprojection_error_mean_m, 4),
            "reprojection_error_max_m": round(self.reprojection_error_max_m, 4),
            "has_validity_mask": self.validity_mask_px is not None,
            "ground_plane_assumption": "flat",
            "nominal_pixel_sigma_px": NOMINAL_PIXEL_SIGMA_PX,
        }
