import copy
import json
import unittest
from datetime import date

from lessons_logic import (
    append_record, archive_record, available_years, default_plan, edit_record,
    forecast, lesson_state, new_record, planned_income, save_metadata,
    student_profiles, year_export, year_plan, year_views,
)
from test_private_lesson_students import namespace


def normalized(records):
    return [namespace["normalize_lesson_record"](record, i)[0] for i, record in enumerate(records)]


class LessonPlanningTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"lessons": [
            {"student": "ron", "date": "2026-12-31", "duration": 1, "total": 130,
             "payment": "bit", "legacy_metadata": {"keep": [1, 2]}},
            {"student": "gal", "date": "2027-01-01", "duration": 1, "total": 150,
             "payment": "bit"},
            {"student": "itamar", "date": "2026-05-18", "duration": 1, "total": 150,
             "payment": "bit", "archived_at": "2026-06-01"},
            {"date": "invalid", "total": 77, "unknown": "retain"},
        ], "students": ["ron", "legacy"], "unknown_state": {"retain": True}}
        self.valid = normalized(self.raw["lessons"][:3])
        self.profiles = student_profiles(self.raw, self.valid)

    def test_rollover_selects_new_year_without_any_state_changes(self):
        before = copy.deepcopy(self.raw)
        active = [v for v in self.valid if not v["_archived"]]
        new_year = date(2027, 1, 1)
        self.assertIn(2026, available_years(self.valid, new_year))
        self.assertEqual(sum(v["total"] for v in year_views(active, 2026)), 130)
        self.assertEqual(sum(v["total"] for v in year_views(active, 2027)), 150)
        plan = year_plan(self.raw, self.profiles, 2027)
        result = forecast(active, plan, 2027, new_year)
        self.assertEqual(sum(r["actual"] for r in result), 150)
        self.assertEqual(self.raw, before)

    def test_closed_year_has_no_future_projection(self):
        rows = forecast(self.valid[:1], year_plan(self.raw, self.profiles, 2026), 2026, date(2027, 1, 1))
        self.assertEqual(sum(r["remaining"] for r in rows), 0)
        self.assertEqual(sum(r["projected"] for r in rows), 130)

    def test_current_month_actual_and_future_days_are_not_double_counted(self):
        p = default_plan("ron", self.profiles["ron"], 2026)
        views = normalized([{"student": "ron", "date": "2026-10-01", "duration": 1,
                             "total": 130, "payment": "bit"}])
        rows = forecast(views, {"students": {"ron": p}}, 2026, date(2026, 10, 17))
        october = rows[9]
        self.assertEqual(october["actual"], 130)
        self.assertAlmostEqual(october["remaining"], 130 * 14 / 31)
        self.assertAlmostEqual(october["projected"], 130 + 130 * 14 / 31)
        self.assertAlmostEqual(october["expected_to_date"], 130 * 17 / 31)

    def test_future_records_are_projected_once_not_counted_as_actual(self):
        views = normalized([{"student": "gal", "date": "2027-01-10", "duration": 1,
                             "total": 150, "payment": "bit"}])
        p = default_plan("gal", self.profiles["gal"], 2027)
        january = forecast(views, {"students": {"gal": p}}, 2027, date(2026, 12, 31))[0]
        self.assertEqual(january["actual"], 0)
        self.assertAlmostEqual(january["remaining"], planned_income(p, 2027, 1))
        p["enabled"] = False
        january = forecast(views, {"students": {"gal": p}}, 2027, date(2026, 12, 31))[0]
        self.assertEqual(january["projected"], 150)

    def test_weekly_46_weeks_and_seasonal_end_resits(self):
        p = default_plan("gal", self.profiles["gal"], 2027)
        self.assertAlmostEqual(sum(planned_income(p, 2027, m) for m in range(1, 13)), 6900)
        p = default_plan("shachar", self.profiles["shachar"], 2027)
        self.assertAlmostEqual(sum(planned_income(p, 2027, m) for m in range(1, 13)), 3300)
        self.assertEqual(planned_income(p, 2027, 8), 0)
        self.assertEqual(planned_income(p, 2027, 9), 0)
        p["include_resits"] = True
        self.assertEqual(planned_income(p, 2027, 8), 900)
        self.assertEqual(planned_income(p, 2027, 8, conservative=True), 0)
        p2028 = default_plan("shachar", self.profiles["shachar"], 2028)
        self.assertEqual(sum(planned_income(p2028, 2028, m) for m in range(1, 13)), 0)

    def test_non_leap_and_leap_year_weekly_weights(self):
        for year in (2027, 2028):
            p = default_plan("gal", self.profiles["gal"], year)
            self.assertAlmostEqual(sum(planned_income(p, year, m) for m in range(1, 13)), 6900)

    def test_profile_and_plan_edits_preserve_every_lesson_and_other_years(self):
        before = copy.deepcopy(self.raw)
        plan2026 = year_plan(self.raw, self.profiles, 2026)
        state = save_metadata(self.raw, "year_plans", {"2026": plan2026})
        profiles = copy.deepcopy(self.profiles)
        profiles["ron"]["default_rate"] = 999
        changed = save_metadata(state, "student_profiles", profiles)
        self.assertEqual(changed["lessons"], before["lessons"])
        self.assertEqual(year_plan(changed, profiles, 2026), plan2026)
        self.assertEqual(changed["unknown_state"], before["unknown_state"])

    def test_edit_archive_restore_and_append_preserve_unknown_history(self):
        before = copy.deepcopy(self.raw)
        edited = edit_record(self.raw, 0, {"total": 200, "price_per_hour": 200}, "now")
        self.assertEqual(edited["lessons"][0]["edit_history"][0]["previous"], before["lessons"][0])
        self.assertEqual(edited["lessons"][1:], before["lessons"][1:])
        archived = archive_record(edited, 0, "later")
        restored = archive_record(archived, 0, "latest", restore=True)
        self.assertNotIn("archived_at", restored["lessons"][0])
        self.assertEqual(restored["lessons"][0]["legacy_metadata"], {"keep": [1, 2]})
        added = append_record(restored, new_record("gal", "", "2027-01-05", 1, 150, "bit", "hours", "now"))
        self.assertEqual(added["lessons"][:-1], restored["lessons"])
        self.assertEqual(self.raw, before)

    def test_export_roundtrip_includes_archived_records_and_history(self):
        before = copy.deepcopy(self.raw)
        result = year_export(self.raw, 2026, year_plan(self.raw, self.profiles, 2026), "now")
        result = json.loads(json.dumps(result))
        self.assertEqual(len(result["lesson_state"]["lessons"]), 2)
        self.assertIn("archived_at", result["lesson_state"]["lessons"][1])
        self.assertEqual(result["lesson_state"]["unknown_state"], before["unknown_state"])
        self.assertEqual(self.raw, before)

    def test_invalid_state_and_amounts_fail_closed(self):
        for bad in (None, {}, {"lessons": {}}, {"lessons": [], "year_plans": []}):
            with self.assertRaises(ValueError):
                lesson_state(bad)
        self.assertEqual(lesson_state(self.raw["lessons"])["lessons"], self.raw["lessons"])
        for amount in (float("nan"), float("inf"), -1, 0):
            with self.assertRaises(ValueError):
                new_record("gal", "", "2027-01-01", 1, amount, "bit", "hours", "now")


if __name__ == "__main__":
    unittest.main()
