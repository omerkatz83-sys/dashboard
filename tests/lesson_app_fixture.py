"""Offline app used by Streamlit AppTest; never connects to the production database."""
import ast
import copy
import json
import math
import os
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from lessons_dashboard import render_lessons_dashboard

source = Path(__file__).resolve().parents[1] / "dashboard_app.py"
nodes = [n for n in ast.parse(source.read_text(encoding="utf-8")).body if (
    isinstance(n, ast.FunctionDef) and n.name in {"normalize_lesson_record", "_lesson_number"}
) or (isinstance(n, ast.Assign) and any(
    isinstance(t, ast.Name) and t.id == "LEGACY_LESSON_STUDENT_ALIASES" for t in n.targets))]
namespace = {"math": math, "datetime": datetime}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)

if "fixture_data" not in st.session_state:
    backup_path = os.environ.get("LESSON_TEST_BACKUP")
    if backup_path:
        st.session_state.fixture_data = json.loads(Path(backup_path).read_text(encoding="utf-8-sig"))[0]["data"]
    else:
        st.session_state.fixture_data = {"lessons": [
            {"student": "ron", "date": "2026-01-02", "duration": 1, "total": 130, "payment": "bit"},
            {"student": "gal", "date": "2026-10-04", "duration": 1, "total": 150, "payment": "bit"},
            {"student": "gal", "date": "2027-01-01", "duration": 1, "total": 150, "payment": "bit"},
            {"student": "shachar", "date": "2026-02-01", "duration": 1.5, "total": 225,
             "payment": "bit", "archived_at": "2026-02-02"},
            {"date": "invalid", "total": 10, "unknown": "preserve"},
        ], "students": ["ron"], "opaque_state": {"must_survive": [1, 2, 3]}}
    st.session_state.fixture_saves = 0


class MemoryDatabase:
    def get_lessons_data(self, default=None):
        if st.session_state.get("fixture_read_failure"):
            return default
        return copy.deepcopy(st.session_state.fixture_data)

    def save_lessons_data(self, data):
        if st.session_state.get("fixture_save_failure"):
            return False
        st.session_state.fixture_data = copy.deepcopy(data)
        st.session_state.fixture_saves += 1
        return True


render_lessons_dashboard(MemoryDatabase(), namespace["normalize_lesson_record"],
                         date.fromisoformat(st.session_state.get("today_override", "2026-10-17")))
