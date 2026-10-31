import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install dashboard dependencies for UI tests")
class ProjectionUITests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(Path(__file__).with_name("projection_app_fixture.py")), default_timeout=30).run()
        self.assertFalse(len(app.exception), str(app.exception))
        return app

    def set_zero_return_one_year(self, app):
        app.slider(key="projection_years").set_value(1)
        app.number_input(key="projection_focus_rate").set_value(0).run()
        self.assertFalse(len(app.exception), str(app.exception))

    def metric(self, app, label):
        return next(m for m in app.metric if m.label == label).value

    def test_live_sources_and_unchanged_funding(self):
        app = self.app()
        self.set_zero_return_one_year(app)
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$112,000")
        self.assertEqual(self.metric(app, "השפעת השינויים על השווי"), "$0")
        self.assertEqual(self.metric(app, "רווח חזוי מהיום בתרחיש שלך"), "$0")

    def test_increasing_monthly_deposits_and_reset(self):
        app = self.app()
        self.set_zero_return_one_year(app)
        app.number_input(key="projection_monthly").set_value(2000).run()
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$124,000")
        self.assertEqual(self.metric(app, "השפעת השינויים על השווי"), "$12,000")
        app.button(key="projection_reset_monthly").click().run()
        self.assertEqual(app.number_input(key="projection_monthly").value, 1000)
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$112,000")

    def test_exclude_cash_and_currency_conversion(self):
        app = self.app()
        self.set_zero_return_one_year(app)
        app.radio(key="projection_start_source").set_value("השקעות בלבד, ללא מזומן").run()
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$92,000")
        app.selectbox(key="projection_currency").set_value("ILS").run()
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "₪276,000")
        self.assertEqual(app.number_input(key="projection_monthly").value, 1000)

    def test_multiple_lumps_and_out_of_horizon_validation(self):
        app = self.app()
        self.set_zero_return_one_year(app)
        app.checkbox(key="projection_use_lumps").check().run()
        app.number_input(key="projection_lump_0_amount").set_value(10000).run()
        app.button(key="projection_add_lump").click().run()
        app.number_input(key="projection_lump_1_amount").set_value(5000)
        app.number_input(key="projection_lump_1_month").set_value(6).run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$127,000")
        app.number_input(key="projection_lump_1_month").set_value(13).run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertTrue(len(app.error))

    def test_negative_return_and_inflation_controls(self):
        app = self.app()
        app.number_input(key="projection_focus_rate").set_value(-5).run()
        app.checkbox(key="projection_adjust_inflation").check().run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(app.number_input(key="projection_inflation").value, 2)
        self.assertTrue(any("כוח הקנייה" in item.value for item in app.info))

    def test_slider_and_quick_actions_stay_synchronized(self):
        app = self.app()
        self.set_zero_return_one_year(app)
        app.slider(key="projection_monthly_slider").set_value(1500).run()
        self.assertEqual(app.number_input(key="projection_monthly").value, 1500)
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$118,000")
        app.button(key="projection_preset_125000").click().run()
        self.assertEqual(app.number_input(key="projection_monthly").value, 1250)
        self.assertEqual(app.slider(key="projection_monthly_slider").value, 1250)
        app.button(key="projection_years_10").click().run()
        self.assertEqual(app.slider(key="projection_years").value, 10)
        self.assertFalse(len(app.exception), str(app.exception))

    def test_remove_lump_toggle_and_reset_preserve_expected_state(self):
        app = self.app()
        self.set_zero_return_one_year(app)
        app.checkbox(key="projection_use_lumps").check().run()
        app.number_input(key="projection_lump_0_amount").set_value(10000).run()
        app.button(key="projection_add_lump").click().run()
        app.number_input(key="projection_lump_1_amount").set_value(5000).run()
        app.button(key="projection_lump_0_remove").click().run()
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$117,000")
        app.checkbox(key="projection_use_lumps").uncheck().run()
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$112,000")
        app.checkbox(key="projection_use_lumps").check().run()
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$117,000")
        app.button(key="projection_reset_all").click().run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(app.number_input(key="projection_monthly").value, 1000)
        self.assertFalse(app.checkbox(key="projection_use_lumps").value)
        self.assertEqual(app.slider(key="projection_years").value, 20)

    def test_time_inspector_and_capital_chart(self):
        app = self.app()
        app.slider(key="projection_inspect_year").set_value(5).run()
        app.checkbox(key="projection_show_capital").check().run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(app.slider(key="projection_inspect_year").value, 5)
        app.slider(key="projection_years").set_value(1).run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(app.slider(key="projection_inspect_year").value, 1)


if __name__ == "__main__":
    unittest.main()
