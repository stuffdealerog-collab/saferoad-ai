"""Milestone 4 — Post-Encroachment Time, strictly zone-based.

PET = time between the FIRST road user leaving a conflict zone and the SECOND
entering it. Defined ONLY relative to a zone (tech plan v2 §7); resolution is
bounded by the actual frame step.

Correctness guards (each refusal carries a reason, never a fake number):
- the first user's exit must be OBSERVED — a track that ended inside the zone
  (occlusion) has an unknown exit time;
- the second user's entry must be OBSERVED — a track that started inside the
  zone has an unknown entry time;
- overlapping occupancies mean simultaneous presence: PET is 0/undefined —
  reported as ``simultaneous_occupancy`` (a *worse* situation than small PET,
  to be scored by the near-miss engine, not hidden).
"""
from __future__ import annotations

from dataclasses import dataclass

from geometry.zones import Occupancy


@dataclass
class PETResult:
    applicable: bool
    zone_id: str
    first: dict | None = None          # occupancy dict of the earlier user
    second: dict | None = None
    pet_s: float | None = None
    resolution_s: float | None = None  # actual frame step: PET precision bound
    reason: str | None = None


def pet_between(a: Occupancy, b: Occupancy, resolution_s: float) -> PETResult:
    """PET between two occupancies of the SAME zone."""
    if a.zone_id != b.zone_id:
        raise ValueError("PET requires occupancies of the same zone")

    # simultaneous presence?
    if a.t_enter_s <= b.t_exit_s and b.t_enter_s <= a.t_exit_s:
        return PETResult(False, a.zone_id, a.to_dict(), b.to_dict(),
                         reason="simultaneous_occupancy", resolution_s=resolution_s)

    first, second = (a, b) if a.t_exit_s <= b.t_enter_s else (b, a)
    if not first.exit_observed:
        return PETResult(False, a.zone_id, first.to_dict(), second.to_dict(),
                         reason="first_exit_unobserved_track_ended_in_zone",
                         resolution_s=resolution_s)
    if not second.enter_observed:
        return PETResult(False, a.zone_id, first.to_dict(), second.to_dict(),
                         reason="second_entry_unobserved_track_started_in_zone",
                         resolution_s=resolution_s)
    return PETResult(
        True, a.zone_id, first.to_dict(), second.to_dict(),
        pet_s=round(second.t_enter_s - first.t_exit_s, 3),
        resolution_s=resolution_s,
    )
