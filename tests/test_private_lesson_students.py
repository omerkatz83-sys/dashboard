"""Check student grouping and form defaults without starting the live dashboard."""
import ast
import copy
import math
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from lessons_logic import student_profiles


SOURCE = Path(__file__).resolve().parents[1] / "dashboard_app.py"
module = ast.parse(SOURCE.read_text(encoding="utf-8"))
nodes = [
    node for node in ast.walk(module)
    if (
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "LEGACY_LESSON_STUDENT_ALIASES"
                for target in node.targets)
    ) or (
        isinstance(node, ast.FunctionDef)
        and node.name in {"_lesson_number", "normalize_lesson_record"}
    )
]
namespace = {"math": math, "datetime": datetime, "st": SimpleNamespace(session_state={})}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
namespace["STUDENTS"] = student_profiles({"lessons": []}, [])
namespace["PAYMENTS"] = {"bit": "ביט", "paybox": "פייבוקס", "מזומן": "מזומן"}
ui_source = SOURCE.with_name("lessons_dashboard.py")
reset = next(n for n in ast.parse(ui_source.read_text(encoding="utf-8")).body
             if isinstance(n, ast.FunctionDef) and n.name == "_reset_add")
exec(compile(ast.Module(body=[reset], type_ignores=[]), str(ui_source), "exec"), namespace)


class PrivateLessonStudentsTests(unittest.TestCase):
    def test_itamar_is_grouped_with_other_without_changing_history(self):
        records = [
            {"student": "itamar", "date": "2026-06-01", "duration": 1, "total": 150,
             "payment": "bit", "id": "one-off", "edit_history": [{"previous": {"total": 100}}]},
            {"student": "other", "student_name": "אור", "date": "2026-06-02", "total": 100},
        ]
        before = copy.deepcopy(records)
        views = []
        for index, record in enumerate(records):
            view, error = namespace["normalize_lesson_record"](record, index)
            self.assertIsNone(error)
            views.append(view)
        self.assertEqual(records, before)
        self.assertEqual(views[0]["student_name"], "איתמר")
        self.assertEqual(views[0]["id"], "one-off")
        self.assertEqual(views[0]["payment"], "bit")
        self.assertEqual(sum(v["total"] for v in views if v["student"] == "other"), 250)
        self.assertEqual(len(views), len(records))
        self.assertNotIn("itamar", namespace["STUDENTS"])
        self.assertNotIn("איתמר", {v["name"] for v in namespace["STUDENTS"].values()})

    def test_archived_itamar_and_custom_names_are_preserved(self):
        record = {"student": "איתמר", "student_name": "איתמר כהן", "date": "2026-06-01",
                  "total": 150, "archived_at": "2026-06-02T12:00:00"}
        before = copy.deepcopy(record)
        view, error = namespace["normalize_lesson_record"](record, 3)
        self.assertIsNone(error)
        self.assertEqual(view["student"], "other")
        self.assertEqual(view["student_name"], "איתמר כהן")
        self.assertTrue(view["_archived"])
        self.assertEqual(record, before)

    def test_selecting_gal_resets_previous_rate_payment_and_mode(self):
        state = namespace["st"].session_state
        state.clear()
        state.update(test_student="gal", test_rate=130.0,
                     test_payment="paybox", test_mode="סכום קבוע")
        namespace["_reset_add"](namespace["STUDENTS"], "test_")
        self.assertEqual(namespace["STUDENTS"]["gal"]["name"], "גל")
        self.assertEqual(state["test_rate"], 150.0)
        self.assertEqual(state["test_payment"], "bit")
        self.assertEqual(state["test_mode"], "שעות × מחיר")
        state["test_student"] = "other"
        namespace["_reset_add"](namespace["STUDENTS"], "test_")
        self.assertEqual(state["test_mode"], "סכום קבוע")
        state["test_student"] = "gal"
        namespace["_reset_add"](namespace["STUDENTS"], "test_")
        self.assertEqual(state["test_rate"], 150.0)


if __name__ == "__main__":
    unittest.main()
