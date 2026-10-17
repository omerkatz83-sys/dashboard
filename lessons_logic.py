"""Lesson planning and immutable state changes. No network or Streamlit dependency."""
import calendar
import copy
import math
import uuid
from datetime import date, datetime, timedelta


DEFAULT_STUDENTS = {
    "ron": {"name": "רון", "emoji": "🧑‍🎓", "default_rate": 130, "default_duration": 1,
            "pattern": "monthly", "frequency": 1},
    "shachar": {"name": "שחר", "emoji": "🧑‍🎓", "default_rate": 150,
                "default_duration": 1, "pattern": "seasonal", "end_date": "2027-08-31"},
    "itay_adva": {"name": "איתי ואדווה", "emoji": "👫", "default_rate": 160,
                  "default_duration": 0.75, "active": False, "pattern": "none"},
    "gal": {"name": "גל", "emoji": "👩‍🎓", "default_rate": 150, "default_duration": 1,
            "default_payment": "bit", "pattern": "weekly", "start_date": "2026-10-04"},
    "karni": {"name": "קרני", "emoji": "👩‍🎓", "default_rate": 150, "default_duration": 1,
              "pattern": "weekly", "start_date": "2026-10-17"},
    "other": {"name": "אחר", "emoji": "👤", "default_rate": 0,
              "default_duration": 1, "pattern": "none"},
}


def number(value, minimum=0, maximum=None):
    result = float(value)
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError("ערך מספרי מחוץ לטווח המותר")
    return result


def lesson_state(raw):
    """Wrap legacy lists; refuse ambiguous or damaged data instead of overwriting it."""
    if isinstance(raw, list):
        return {"lessons": copy.deepcopy(raw)}
    if not isinstance(raw, dict) or not isinstance(raw.get("lessons"), list):
        raise ValueError("נתוני השיעורים לא נטענו בצורה תקינה. פעולות שמירה הושבתו.")
    for key in ("student_profiles", "year_plans"):
        if key in raw and not isinstance(raw[key], dict):
            raise ValueError(f"מבנה {key} אינו תקין. הנתונים נשמרו ללא שינוי.")
    return copy.deepcopy(raw)


def student_profiles(state, views):
    profiles = copy.deepcopy(DEFAULT_STUDENTS)
    for key, stored in state.get("student_profiles", {}).items():
        if not isinstance(stored, dict):
            raise ValueError("הגדרת תלמיד אינה תקינה")
        profiles.setdefault(key, {})
        profiles[key].update(copy.deepcopy(stored))
    for view in views:
        key = view["student"]
        if key not in profiles:
            profiles[key] = {"name": view.get("student_name") or key,
                             "default_rate": view.get("price_per_hour", 0),
                             "active": False, "pattern": "none"}
    for profile in profiles.values():
        profile.setdefault("emoji", "👤")
        profile.setdefault("active", True)
        profile.setdefault("default_duration", 1)
        profile.setdefault("default_payment", "bit")
        profile.setdefault("frequency", 1)
        profile.setdefault("weeks_per_year", 46)
        profile.setdefault("start_date", "2000-01-01")
        profile.setdefault("end_date", "")
        number(profile["default_rate"])
        number(profile["default_duration"], 0.25, 10)
    return profiles


def available_years(views, today, saved_plans=None):
    years = {today.year, today.year + 1}
    years.update(int(v["date"][:4]) for v in views)
    years.update(int(y) for y in (saved_plans or {}) if str(y).isdigit())
    return sorted(years, reverse=True)


def year_views(views, year):
    return sorted((v for v in views if v["date"].startswith(f"{year}-")),
                  key=lambda v: (v["date"], v["_source_index"]))


def default_plan(key, profile, year):
    hours = {str(m): 7 / 3 for m in range(1, 13)}
    if key == "shachar" and year >= 2027:
        hours.update({"7": 8, "8": 0, "9": 0, "10": 0, "11": 0, "12": 0})
    return {"enabled": profile["active"] and profile.get("pattern", "none") != "none",
            "pattern": profile.get("pattern", "none"), "rate": profile["default_rate"],
            "duration": profile["default_duration"], "frequency": profile["frequency"],
            "weeks_per_year": profile["weeks_per_year"], "conservative_factor": 0.85,
            "start_date": max(f"{year}-01-01", profile["start_date"]),
            "end_date": min(f"{year}-12-31", profile["end_date"] or f"{year}-12-31"),
            "monthly_hours": hours, "include_resits": False, "resit_hours": 6}


def year_plan(state, profiles, year):
    saved = state.get("year_plans", {}).get(str(year), {})
    if not isinstance(saved, dict) or not isinstance(saved.get("students", {}), dict):
        raise ValueError("מבנה התכנון השנתי אינו תקין")
    result = copy.deepcopy(saved)
    result.setdefault("goal_enabled", False)
    result.setdefault("goal_amount", 20000)
    result["students"] = {}
    for key, profile in profiles.items():
        result["students"][key] = default_plan(key, profile, year)
        result["students"][key].update(copy.deepcopy(saved.get("students", {}).get(key, {})))
    return result


def planned_income(plan, year, month, start=None, end=None, conservative=False):
    if not plan.get("enabled") or plan.get("pattern") == "none":
        return 0.0
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    left = max(month_start, date.fromisoformat(plan["start_date"]), start or month_start)
    right = min(month_end, date.fromisoformat(plan["end_date"]), end or month_end)
    if right < left:
        return 0.0
    days = (right - left).days + 1
    rate = number(plan["rate"])
    pattern = plan["pattern"]
    if pattern == "weekly":
        hours = (number(plan["frequency"]) * number(plan["duration"])
                 * number(plan["weeks_per_year"], maximum=53)
                 * days / (366 if calendar.isleap(year) else 365))
    elif pattern == "monthly":
        hours = number(plan["frequency"]) * number(plan["duration"]) * days / month_end.day
    elif pattern == "seasonal":
        hours = number(plan["monthly_hours"].get(str(month), 0)) * days / month_end.day
    else:
        raise ValueError("סוג תכנון לא מוכר")
    amount = hours * rate
    if conservative:
        amount *= number(plan["conservative_factor"], maximum=1)
    elif pattern == "seasonal" and month == 8 and plan.get("include_resits"):
        amount += number(plan.get("resit_hours", 0)) * days / month_end.day * rate
    return amount


def forecast(views, plan, year, today):
    """Keep actuals to today; project only remaining days, including partial months."""
    rows = []
    remaining_start = today + timedelta(days=1)
    for month in range(1, 13):
        month_views = [v for v in year_views(views, year) if int(v["date"][5:7]) == month]
        completed = [v for v in month_views if v["date"] <= today.isoformat()]
        scheduled = [v for v in month_views if v["date"] > today.isoformat()]
        actual = sum(v["total"] for v in completed)
        base = low = expected = elapsed = 0.0
        keys = set(plan["students"]) | {v["student"] for v in scheduled}
        for key in keys:
            future_recorded = sum(v["total"] for v in scheduled if v["student"] == key)
            student_plan = plan["students"].get(key)
            if student_plan:
                expected += planned_income(student_plan, year, month)
                elapsed += planned_income(student_plan, year, month, end=today)
                base += max(future_recorded, planned_income(student_plan, year, month, start=remaining_start))
                low += max(future_recorded, planned_income(student_plan, year, month,
                                                         start=remaining_start, conservative=True))
            else:
                base += future_recorded
                low += future_recorded
        rows.append({"month": f"{year}-{month:02d}", "actual": actual,
                     "hours": sum(v["duration"] for v in completed), "count": len(completed),
                     "expected": expected, "expected_to_date": elapsed,
                     "remaining": base, "conservative_remaining": low,
                     "projected": actual + base, "conservative": actual + low,
                     "gap": actual - elapsed, "scheduled": sum(v["total"] for v in scheduled)})
    return rows


def duplicate_matches(views, candidate, exclude_index=None):
    return [v for v in views if v["_source_index"] != exclude_index
            and v["student"] == candidate["student"]
            and v.get("student_name", "").strip() == candidate.get("student_name", "").strip()
            and v["date"] == candidate["date"]
            and abs(v["total"] - candidate["total"]) < 0.005
            and abs(v["duration"] - candidate["duration"]) < 0.005]


def new_record(student, student_name, lesson_date, duration, total, payment, mode, now):
    if payment not in {"bit", "paybox", "מזומן"}:
        raise ValueError("אמצעי תשלום אינו תקין")
    duration = number(duration, maximum=10)
    total = number(total, minimum=0.01)
    return {"id": uuid.uuid4().hex, "student": student,
            "student_name": student_name.strip() if student == "other" else "",
            "date": date.fromisoformat(lesson_date).isoformat(), "duration": round(duration, 2),
            "total": round(total, 2), "price_per_hour": round(total / duration, 2) if duration else 0,
            "payment": payment, "mode": mode, "created_at": now}


def append_record(state, record):
    updated = copy.deepcopy(state)
    updated["lessons"].append(copy.deepcopy(record))
    return updated


def edit_record(state, index, values, now):
    updated = copy.deepcopy(state)
    record = updated["lessons"][index]
    history = record.get("edit_history", [])
    if not isinstance(history, list):
        raise ValueError("היסטוריית העריכות אינה תקינה; הרשומה לא שונתה")
    # Snapshot all original fields except the history itself, including unknown legacy metadata.
    previous = {k: copy.deepcopy(v) for k, v in record.items() if k != "edit_history"}
    record["edit_history"] = copy.deepcopy(history) + [{"edited_at": now, "previous": previous}]
    record.update(copy.deepcopy(values))
    record["id"] = record.get("id") or uuid.uuid4().hex
    record["updated_at"] = now
    return updated


def archive_record(state, index, now, restore=False):
    updated = copy.deepcopy(state)
    record = updated["lessons"][index]
    history = record.setdefault("archive_history", [])
    if not isinstance(history, list):
        raise ValueError("היסטוריית הארכיון אינה תקינה")
    history.append({"archived_at": record.get("archived_at") if restore else now,
                    "restored_at": now if restore else None})
    if restore:
        record.pop("archived_at", None)
        record.pop("archive_reason", None)
        record["restored_at"] = now
    else:
        record["archived_at"] = now
        record["archive_reason"] = "user_requested"
    return updated


def save_metadata(state, key, value):
    updated = copy.deepcopy(state)
    updated[key] = copy.deepcopy(value)
    return updated


def year_export(state, year, plan, now):
    exported = copy.deepcopy(state)
    exported["lessons"] = [copy.deepcopy(v) for v in state["lessons"]
                           if isinstance(v, dict) and str(v.get("date", "")).startswith(f"{year}-")]
    exported["year_plans"] = {str(year): copy.deepcopy(plan)}
    return {"format_version": 1, "year": year, "exported_at": now,
            "lesson_state": exported}
