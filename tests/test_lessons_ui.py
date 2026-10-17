import copy
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install dashboard dependencies to run Streamlit UI tests")
class LessonsUITests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(Path(__file__).with_name("lesson_app_fixture.py")), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        return app

    def by_label(self, elements, label):
        return next(e for e in elements if e.label == label)

    def test_read_only_year_rollover_and_history(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        self.assertEqual(app.metric[0].value, "₪280")
        self.assertEqual(app.session_state["fixture_saves"], 0)
        app.session_state["today_override"] = "2027-01-01"
        app.run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertEqual(app.selectbox(key="lessons_year_2027").value, 2027)
        self.assertEqual(app.metric[0].value, "₪150")
        app.selectbox(key="lessons_year_2027").set_value(2026).run()
        self.assertEqual(app.metric[0].value, "₪280")
        self.assertEqual(app.session_state["fixture_data"], original)

    def test_student_defaults_duplicate_guard_and_confirmed_append(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        app.selectbox(key="lesson_add_2026_student").set_value("gal").run()
        self.assertEqual(app.number_input(key="lesson_add_2026_rate").value, 150.0)
        app.button(key="lesson_add_2026_repeat").click().run()
        self.assertEqual(app.session_state["fixture_saves"], 0)
        from datetime import date
        app.date_input(key="lesson_add_2026_date").set_value(date(2026, 10, 4)).run()
        self.assertTrue(app.button(key="lesson_add_2026_save").disabled)
        app.checkbox(key="lesson_add_2026_duplicate").check().run()
        app.button(key="lesson_add_2026_save").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertEqual(app.session_state["fixture_data"]["lessons"][:-1], original["lessons"])
        self.assertEqual(app.session_state["fixture_data"]["opaque_state"], original["opaque_state"])
        self.assertEqual(app.session_state["fixture_saves"], 1)

    def test_saving_year_plan_preserves_every_record(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        app.selectbox(key="lessons_year_2026").set_value(2027).run()
        app.selectbox(key="plan_student_2027").set_value("shachar").run()
        app.checkbox(key="plan_2027_shachar_resits").check()
        self.by_label(app.button, "💾 שמור תכנון לתלמיד ולשנה").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        stored = app.session_state["fixture_data"]
        self.assertEqual(stored["lessons"], original["lessons"])
        self.assertTrue(stored["year_plans"]["2027"]["students"]["shachar"]["include_resits"])
        self.assertEqual(app.session_state["fixture_saves"], 1)

    def test_profile_save_updates_add_defaults_without_repricing_history(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        app.selectbox(key="lesson_add_2026_student").set_value("gal").run()
        app.selectbox(key="student_settings_select").set_value("gal").run()
        self.by_label(app.number_input, "מחיר ברירת מחדל לשעה (₪)").set_value(170)
        self.by_label(app.button, "💾 שמור תלמיד").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertEqual(app.number_input(key="lesson_add_2026_rate").value, 170)
        self.assertEqual(app.session_state["fixture_data"]["lessons"], original["lessons"])

    def test_save_failure_preserves_records_and_reports_error(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        app.session_state["fixture_save_failure"] = True
        app.selectbox(key="lesson_add_2026_student").set_value("gal").run()
        app.button(key="lesson_add_2026_save").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertTrue(len(app.error))
        self.assertEqual(app.session_state["fixture_data"], original)
        self.assertEqual(app.session_state["fixture_saves"], 0)


    def test_edit_archive_and_restore_preserve_years_and_history(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        app.number_input(key="edit_2026_0_total").set_value(140)
        self.by_label(app.button, "💾 שמור עריכה").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        updated = app.session_state["fixture_data"]
        self.assertEqual(updated["lessons"][0]["total"], 140)
        self.assertEqual(updated["lessons"][0]["edit_history"][0]["previous"], original["lessons"][0])
        self.assertEqual(updated["lessons"][1:], original["lessons"][1:])
        app.checkbox(key="edit_2026_0_archive_confirm").check().run()
        app.button(key="edit_2026_0_archive").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertIn("archived_at", app.session_state["fixture_data"]["lessons"][0])
        self.assertEqual(app.metric[0].value, "₪150")
        app.selectbox(key="restore_record_2026").set_value(0).run()
        app.button(key="restore_2026").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertEqual(app.metric[0].value, "₪290")
        self.assertNotIn("archived_at", app.session_state["fixture_data"]["lessons"][0])

    def test_new_student_and_goal_are_persistent_and_year_specific(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        self.by_label(app.text_input, "שם התלמיד/ה").set_value("תלמידת בדיקה")
        self.by_label(app.button, "💾 שמור תלמיד").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        stored = app.session_state["fixture_data"]
        self.assertEqual(stored["lessons"], original["lessons"])
        new_key = next(iter(stored["student_profiles"]))
        app.selectbox(key="lesson_add_2026_student").set_value(new_key).run()
        self.assertEqual(app.number_input(key="lesson_add_2026_rate").value, 150)
        app.selectbox(key="lessons_year_2026").set_value(2027).run()
        app.checkbox(key="goal_enabled_2027").check()
        self.by_label(app.button, "שמור הגדרת יעד").click().run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertTrue(app.session_state["fixture_data"]["year_plans"]["2027"]["goal_enabled"])
        app.selectbox(key="lessons_year_2026").set_value(2026).run()
        self.assertFalse(app.checkbox(key="goal_enabled_2026").value)
        self.assertEqual(app.session_state["fixture_data"]["lessons"], original["lessons"])

    def test_read_failure_blocks_writes(self):
        app = self.app()
        original = copy.deepcopy(app.session_state["fixture_data"])
        app.session_state["fixture_read_failure"] = True
        app.run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertTrue(len(app.error))
        self.assertFalse(any(button.label == "✅ שמור שיעור" for button in app.button))
        self.assertEqual(app.session_state["fixture_data"], original)

    def test_stale_browser_write_is_rejected(self):
        app = self.app()
        changed = copy.deepcopy(app.session_state["fixture_data"])
        changed["opaque_state"]["newer_change"] = True
        from unittest.mock import patch
        from lessons_dashboard import _persist
        class ChangedDatabase:
            def get_lessons_data(self, default=None):
                return changed
            def save_lessons_data(self, data):
                raise AssertionError("must not write stale data")
        with patch("lessons_dashboard.st.error") as error:
            self.assertFalse(_persist(ChangedDatabase(), app.session_state["fixture_data"], {}))
            error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
