"""
Tests for susceptibility.fluvial (per pixel since item 26 Phase 1a).
Verifies the HAND scoring and, critically, that missing/unavailable rasters
never silently produce a fabricated susceptibility score.
"""

import numpy as np
import pytest

from susceptibility.fluvial import compute_fluvial_susceptibility
from susceptibility.inputs import surface


def _hand_context(**overrides):
    base = {
        "status": "available",
        "mean_hnd_m": 3.403,
        "min_hnd_m": 0.0,
        "max_hnd_m": 13.3,
        "river_connectivity": True,
        "max_upstream_area_km2": 75.941,
        "buffer_km": 3.0,
    }
    base.update(overrides)
    return base


def _rasters(hand, upa=None):
    hand = np.atleast_2d(np.asarray(hand, dtype=float))
    layers = {"hand_m": surface(hand, "MERIT/Hydro/v1_0_1", "hnd, bilinear", "experimental")}
    if upa is not None:
        layers["upa_near_km2"] = surface(np.full(hand.shape, upa), "MERIT/Hydro/v1_0_1",
                                         "upa focal max", "experimental")
    return {"status": "available", "shape": hand.shape, "errors": {}, "layers": layers}


class TestComputeFluvialSusceptibility:

    def test_unavailable_rasters_return_insufficient_evidence(self):
        """If MERIT Hydro failed upstream, this must NEVER produce a
        score -- missing data must not become a susceptibility value."""
        result = compute_fluvial_susceptibility(None, {"status": "unavailable"})

        assert result["status"] == "insufficient_evidence"
        assert "aoi_mean_score" not in result
        assert "MERIT" in result["reason"]

    def test_low_hand_produces_high_susceptibility(self):
        """Real Dharavi-like case: low HAND (near drainage) -> high score."""
        result = compute_fluvial_susceptibility(_rasters([[3.403]]), _hand_context())

        assert result["status"] == "experimental"
        assert result["aoi_mean_score"] > 0.7
        assert result["aoi_mean_class"] in ("high", "very_high")

    def test_high_hand_produces_low_susceptibility(self):
        """A pixel far above nearest drainage should score low."""
        result = compute_fluvial_susceptibility(_rasters([[28.0]]))

        assert result["aoi_mean_score"] < 0.2
        assert result["aoi_mean_class"] in ("very_low", "low")

    def test_score_clamped_to_valid_range(self):
        """HAND of 0m (or negative, as MERIT has) clamps to 1.0, not beyond."""
        m = compute_fluvial_susceptibility(_rasters([[0.0, -2.0, 90.0]]))["susceptibility_map"]
        assert m.tolist() == [[1.0, 1.0, 0.0]]

    def test_true_hand_flag_and_spatial_map(self):
        """Distinguishes this from relative_elevation_proxy (true_hand=False),
        and it is now a per-pixel map, not an AOI-wide scalar."""
        result = compute_fluvial_susceptibility(_rasters([[3.0, 15.0]]))
        assert result["true_hand"] is True
        assert result["spatial"] is True
        m = result["susceptibility_map"]
        assert m[0, 0] > m[0, 1]

    def test_not_river_connected_adds_explicit_caveat(self):
        """When river_connectivity is False, the limitations list must
        explicitly say so -- a user should not read a high score without
        this caveat if connectivity is doubtful."""
        hand_context = _hand_context(river_connectivity=False, max_upstream_area_km2=0.02)
        result = compute_fluvial_susceptibility(_rasters([[3.0]]), hand_context)

        caveat_present = any(
            "river-connected" in lim.lower() or "upstream" in lim.lower()
            for lim in result["limitations"]
        )
        assert caveat_present

    def test_never_claims_fabdem_derivation(self):
        """Regression guard for the Section-6 conflation warning: the
        limitations must explicitly state this HAND is NOT from FABDEM."""
        result = compute_fluvial_susceptibility(_rasters([[3.0]]))
        conflation_warning_present = any(
            "fabdem" in lim.lower() for lim in result["limitations"]
        )
        assert conflation_warning_present

    def test_river_size_enters_only_through_its_weight(self):
        r = _rasters([[10.0]], upa=10000.0)
        hand_only = compute_fluvial_susceptibility(r, weights={"low_hand": 1.0, "river_size": 0.0})
        assert hand_only["components_used"] == ["low_hand"]
        both = compute_fluvial_susceptibility(r, weights={"low_hand": 1.0, "river_size": 1.0})
        # (2/3 + 1) / 2: river_size is 1 at the 10,000 km^2 ceiling
        assert both["aoi_mean_score"] == pytest.approx((1 - 10 / 30 + 1.0) / 2, abs=1e-4)
