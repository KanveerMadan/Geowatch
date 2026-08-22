"""
Phase 5: tests for susceptibility.fluvial. Verifies the HAND-threshold
classification and, critically, that missing/unavailable HAND context
never silently produces a fabricated susceptibility score.
"""

import pytest

from susceptibility.fluvial import compute_fluvial_susceptibility


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


class TestComputeFluvialSusceptibility:

    def test_unavailable_hand_returns_insufficient_evidence(self):
        """If MERIT Hydro failed upstream, this must NEVER produce a
        score -- missing data must not become a susceptibility value."""
        hand_context = {"status": "unavailable", "error": "simulated failure"}
        result = compute_fluvial_susceptibility(hand_context)

        assert result["status"] == "insufficient_evidence"
        assert "aoi_mean_score" not in result
        assert "simulated failure" in result["reason"]

    def test_low_hand_produces_high_susceptibility(self):
        """Real Dharavi-like case: low HAND (near drainage) -> high score."""
        hand_context = _hand_context(mean_hnd_m=3.403)
        result = compute_fluvial_susceptibility(hand_context)

        assert result["status"] == "experimental"
        assert result["aoi_mean_score"] > 0.7
        assert result["aoi_mean_class"] in ("high", "very_high")

    def test_high_hand_produces_low_susceptibility(self):
        """A pixel far above nearest drainage should score low."""
        hand_context = _hand_context(mean_hnd_m=28.0)
        result = compute_fluvial_susceptibility(hand_context)

        assert result["aoi_mean_score"] < 0.2
        assert result["aoi_mean_class"] in ("very_low", "low")

    def test_score_clamped_to_valid_range(self):
        """HAND of 0m should clamp to score=1.0, not exceed it."""
        hand_context = _hand_context(mean_hnd_m=0.0)
        result = compute_fluvial_susceptibility(hand_context)

        assert 0.0 <= result["aoi_mean_score"] <= 1.0

    def test_true_hand_flag_always_true_when_available(self):
        """Distinguishes this from relative_elevation_proxy, which must
        always report true_hand=False."""
        result = compute_fluvial_susceptibility(_hand_context())
        assert result["true_hand"] is True
        assert result["spatial"] is False  # AOI-wide scalar, not yet spatial

    def test_not_river_connected_adds_explicit_caveat(self):
        """When river_connectivity is False, the limitations list must
        explicitly say so -- a user should not read a high score without
        this caveat if connectivity is doubtful."""
        hand_context = _hand_context(river_connectivity=False, max_upstream_area_km2=0.02)
        result = compute_fluvial_susceptibility(hand_context)

        caveat_present = any(
            "river-connected" in lim.lower() or "upstream" in lim.lower()
            for lim in result["limitations"]
        )
        assert caveat_present

    def test_never_claims_fabdem_derivation(self):
        """Regression guard for the Section-6 conflation warning: the
        limitations must explicitly state this HAND is NOT from FABDEM."""
        result = compute_fluvial_susceptibility(_hand_context())
        conflation_warning_present = any(
            "fabdem" in lim.lower() for lim in result["limitations"]
        )
        assert conflation_warning_present