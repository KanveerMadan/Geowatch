"""Synthetic sensor cases, with no real event coordinates or reference lookup."""
import unittest

import numpy as np

from experiments.urban_flood_ref.detector import Method, State, detect, detect_summary


class TestSensorEvidence(unittest.TestCase):
    def setUp(self):
        shape = (32, 36)
        self.pre_vv = np.full((5,) + shape, -10.)
        self.pre_vh = np.full((5,) + shape, -17.)
        self.vv = self.pre_vv[0].copy()
        self.vh = self.pre_vh[0].copy()
        self.built = np.zeros(shape)
        self.built[:, 7:20] = .5
        self.ctx = dict(built_fraction=self.built, slope_deg=0., occurrence_pct=0.)

    def apply(self, **kwargs):
        return detect(self.pre_vv, self.pre_vh, self.vv, self.vh, **(self.ctx | kwargs))

    def water(self):
        self.vv[12:16, 3:6] = -18.
        self.vh[12:16, 3:6] = -25.

    def walls(self):
        self.vv[12:16, 9:13] = -5.

    def test_dark_patch_and_corroborated_walls(self):
        self.water()
        self.walls()
        r = self.apply()
        self.assertEqual(r["state"][13, 4], State.FLOODED)
        self.assertEqual(r["state"][13, 10], State.FLOODED)
        self.assertEqual(r["baseline_state"][13, 10], State.AMBIGUOUS)
        self.assertTrue(r["method"][13, 10] & Method.URBAN_BRIGHTENING)
        self.assertTrue(r["method"][13, 10] & Method.NEAR_DARKENING)
        self.assertGreaterEqual(r["confidence"][13, 10], .5)
        self.assertEqual(r["state"][13, 16], State.AMBIGUOUS)

    def test_urban_quiet_and_isolated_bright_returns_abstain(self):
        self.walls()
        r = self.apply()
        self.assertEqual(r["state"][14, 10], State.AMBIGUOUS)
        self.assertEqual(r["state"][25, 10], State.AMBIGUOUS)
        self.assertEqual(r["confidence"][14, 10], 0.)
        self.water()
        self.vv[12:16, 9:13] = -10.
        self.vv[14, 10] = -4.
        self.assertEqual(self.apply()["state"][14, 10], State.AMBIGUOUS)

    def test_rain_like_both_polarizations_do_not_confirm_walls(self):
        self.water()
        self.walls()
        self.vh[12:16, 9:13] += 5.
        self.assertEqual(self.apply()["state"][13, 10], State.AMBIGUOUS)

    def test_coherence_must_have_anchor_and_baseline_coherence(self):
        pre = np.full_like(self.vv, .8)
        event = pre.copy()
        event[12:16, 9:13] = .25
        self.assertEqual(self.apply(coherence_pre=pre, coherence_event=event)["state"][14, 10], State.AMBIGUOUS)
        self.walls()
        r = self.apply(coherence_pre=pre, coherence_event=event)
        self.assertTrue(r["method"][14, 10] & Method.COHERENCE_DROP)
        self.assertEqual(r["state"][14, 10], State.FLOODED)
        pre[:] = .5
        self.assertEqual(self.apply(coherence_pre=pre, coherence_event=event)["state"][14, 10], State.AMBIGUOUS)
        with self.assertRaises(ValueError):
            self.apply(coherence_event=event)

    def test_unobserved_and_independent_dry_confirmation(self):
        self.water()
        occ = np.zeros_like(self.vv)
        occ[12:16, 3:6] = 80.
        self.pre_vv[:3, 1, 0] = np.nan
        self.pre_vh[3:, 1, 0] = np.nan
        self.vh[2, 0] = np.nan
        visible = np.ones_like(self.vv)
        visible[3, 0] = np.nan
        self.built[4, 0] = np.nan
        r = self.apply(occurrence_pct=occ, terrain_visible=visible, dry_evidence=True)
        for y,x in [(14, 4), (1,0), (2,0), (3,0), (4,0)]:
            self.assertEqual(r["state"][y, x], State.UNOBSERVED)
            self.assertTrue(np.isnan(r["confidence"][y, x]))
        self.assertEqual(r["state"][23,15], State.DRY)
        self.assertTrue(r["method"][23,15] & Method.MEASURED_DRY)

    def test_inconsistent_dry_observation_or_noisy_history_abstains(self):
        self.water()
        self.walls()
        r = self.apply(dry_evidence=True)
        self.assertEqual(r["state"][14, 4], State.AMBIGUOUS)
        self.assertEqual(r["state"][14, 10], State.AMBIGUOUS)
        for i, value in enumerate([-6.,-3.,0.,3.,6.]):
            self.pre_vv[i,:,7:20] += value
        self.assertEqual(self.apply()["state"][14, 10], State.AMBIGUOUS)

    def test_spatial_filters_do_not_join_opposite_edges(self):
        self.built[:, -3:] = .9
        self.vv[12:16, :3] = -20.
        self.vh[12:16, :3] = -26.
        self.vv[12:16, -3:] = -4.
        r = self.apply()
        self.assertEqual(r["state"][14,-1], State.AMBIGUOUS)

    def test_open_land_is_opt_in_and_cannot_override_an_urban_abstention(self):
        self.assertEqual(self.apply()["state"][25, 2], State.AMBIGUOUS)
        eligible = np.ones_like(self.vv)
        eligible[24, 2] = np.nan
        r = self.apply(open_land=eligible)
        self.assertEqual(r["state"][25, 2], State.DRY)
        self.assertTrue(r["method"][25, 2] & Method.STABLE_OPEN_LAND)
        self.assertEqual(r["state"][24, 2], State.AMBIGUOUS)
        self.assertEqual(r["state"][25, 15], State.AMBIGUOUS)

    def test_summary_agrees_on_valid_joint_observations(self):
        self.walls()
        self.water()
        self.pre_vh[0,0,0] = np.nan
        count = np.isfinite(self.pre_vh).sum(axis=0)
        a = self.apply()
        b = detect_summary(-10., -17., 0., 0., count, self.vv, self.vh, **self.ctx)
        for k in a:
            np.testing.assert_equal(a[k], b[k])
        self.assertEqual(np.count_nonzero(self.apply()["state"] == State.FLOODED), 28)


if __name__ == "__main__":
    unittest.main()
