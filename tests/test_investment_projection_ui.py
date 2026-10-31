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
        app.session_state["fixture_lumps"] = {"בעוד חודשים": [0, 6], "סכום ($)": [10000.0, 5000.0]}
        app.checkbox(key="projection_use_lumps").check().run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(self.metric(app, "התרחיש שלך — שווי עתידי"), "$127,000")
        app.session_state["fixture_lumps"] = {"בעוד חודשים": [13], "סכום ($)": [10000.0]}
        app.run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertTrue(len(app.error))

    def test_negative_return_and_inflation_controls(self):
        app = self.app()
        app.number_input(key="projection_focus_rate").set_value(-5).run()
        app.checkbox(key="projection_adjust_inflation").check().run()
        self.assertFalse(len(app.exception), str(app.exception))
        self.assertEqual(app.number_input(key="projection_inflation").value, 2)
        self.assertTrue(any("כוח הקנייה" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
