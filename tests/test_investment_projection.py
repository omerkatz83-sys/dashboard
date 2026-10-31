import copy
import math
import unittest

from investment_projection import annual_to_monthly, compare_funding, project_investment


class InvestmentProjectionTests(unittest.TestCase):
    def test_effective_annual_return_is_preserved(self):
        self.assertAlmostEqual((1 + annual_to_monthly(7)) ** 12, 1.07)
        self.assertAlmostEqual(project_investment(1000, 0, 12, 7)[-1]["balance"], 1070)

    def test_zero_return_is_all_capital_not_profit(self):
        rows = project_investment(1000, 100, 12, 0, lump_sums=[{"month": 0, "amount": 200}, {"month": 6, "amount": 300}])
        final = rows[-1]
        self.assertEqual(final["balance"], 2700)
        self.assertEqual(final["future_deposits"], 1700)
        self.assertTrue(all(row["growth"] == 0 for row in rows))

    def test_end_of_month_contributions_match_annuity_formula(self):
        annual_pct = ((1.01 ** 12) - 1) * 100
        final = project_investment(1000, 100, 12, annual_pct)[-1]
        expected = 1000 * 1.01 ** 12 + 100 * (1.01 ** 12 - 1) / 0.01
        self.assertAlmostEqual(final["balance"], expected)
        self.assertEqual(final["capital"], 2200)
        self.assertAlmostEqual(final["growth"], expected - 2200)

    def test_delayed_contribution_change_begins_after_full_wait(self):
        rows = project_investment(0, 100, 24, 0, changed_monthly=200, change_after_months=12)
        self.assertEqual(rows[12]["balance"], 1200)
        self.assertEqual(rows[13]["balance"], 1400)
        self.assertEqual(rows[24]["balance"], 3600)

    def test_lump_now_grows_but_final_month_lump_does_not(self):
        now = project_investment(0, 0, 12, 10, lump_sums=[{"month": 0, "amount": 1000}])
        later = project_investment(0, 0, 12, 10, lump_sums=[{"month": 12, "amount": 1000}])
        self.assertAlmostEqual(now[-1]["balance"], 1100)
        self.assertEqual(later[-1]["balance"], 1000)
        self.assertAlmostEqual(now[-1]["growth"], 100)
        self.assertEqual(later[-1]["growth"], 0)

    def test_multiple_lumps_in_same_month_are_aggregated_without_mutation(self):
        lumps = [{"month": 6, "amount": 100}, {"month": 6, "amount": 200}]
        original = copy.deepcopy(lumps)
        rows = project_investment(0, 0, 12, 0, lump_sums=lumps)
        self.assertEqual(rows[5]["balance"], 0)
        self.assertEqual(rows[6]["balance"], 300)
        self.assertEqual(rows[-1]["balance"], 300)
        self.assertEqual(lumps, original)

    def test_negative_returns_show_loss_separately_from_deposits(self):
        final = project_investment(1000, 0, 12, -20)[-1]
        self.assertAlmostEqual(final["balance"], 800)
        self.assertAlmostEqual(final["growth"], -200)

    def test_reduced_contributions_and_combined_effects(self):
        result = compare_funding(10000, 500, 120, 7, 0, 12, [{"month": 2, "amount": 3000}])
        last = {k: path[-1] for k, path in result.items()}
        self.assertLess(last["monthly_only"]["balance"], last["baseline"]["balance"])
        difference = last["combined"]["balance"] - last["baseline"]["balance"]
        summed_effect = (last["monthly_only"]["balance"] - last["baseline"]["balance"]
                         + last["lumps_only"]["balance"] - last["baseline"]["balance"])
        self.assertAlmostEqual(difference, summed_effect)

    def test_inflation_adjusts_purchasing_power_only(self):
        final = project_investment(1000, 0, 12, 10, annual_inflation_pct=10)[-1]
        self.assertAlmostEqual(final["real_value"], 1000)
        self.assertAlmostEqual(final["balance"], 1100)

    def test_invalid_or_out_of_horizon_inputs_are_rejected(self):
        for rate in (-100, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                project_investment(1000, 100, 12, rate)
        for row in ({"month": 13, "amount": 100}, {"month": 1.5, "amount": 100},
                    {"month": -1, "amount": 100}, {"month": 1, "amount": -100}):
            with self.assertRaises(ValueError):
                project_investment(1000, 100, 12, 7, lump_sums=[row])
        for initial in (-1, float("nan")):
            with self.assertRaises(ValueError):
                project_investment(initial, 100, 12, 7)

    def test_month_zero_and_long_horizon_have_consistent_totals(self):
        start = project_investment(1000, 100, 0, 7, lump_sums=[{"month": 0, "amount": 500}])
        self.assertEqual(start[0]["balance"], 1500)
        self.assertEqual(start[0]["growth"], 0)
        final = project_investment(100000, 2000, 600, 12)[-1]
        self.assertTrue(math.isfinite(final["balance"]))
        self.assertEqual(final["future_deposits"], 1200000)
        self.assertAlmostEqual(final["balance"], final["capital"] + final["growth"])


if __name__ == "__main__":
    unittest.main()
