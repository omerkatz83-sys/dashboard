"""Year-aware private lessons workspace; all stored lesson history stays intact."""
import copy
import json
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lessons_logic import (
    append_record, archive_record, available_years, duplicate_matches, edit_record,
    forecast, lesson_state, new_record, save_metadata, student_profiles,
    year_export, year_plan, year_views,
)


PAYMENTS = {"bit": "📱 ביט", "paybox": "📲 פייבוקס", "מזומן": "💵 מזומן"}
PATTERNS = {"weekly": "שבועי", "monthly": "חודשי", "seasonal": "לפי שעות בכל חודש", "none": "ללא תחזית"}


def _persist(db, original, updated):
    """Refuse stale browser writes or read errors; never replace unread data."""
    latest = db.get_lessons_data({"_read_failed": True})
    if latest != original:
        st.error("הנתונים השתנו או שהחיבור נכשל. רענן את הדף לפני שמירה כדי לשמור על כל העדכונים.")
        return False
    if not db.save_lessons_data(updated):
        st.error("השמירה נכשלה. השינוי לא הוחל בתצוגה; נסה שוב לאחר בדיקת החיבור.")
        return False
    st.session_state["lessons_saved_notice"] = "✅ העדכון נשמר."
    st.rerun()
    return True


def _display_name(view, profiles):
    return view.get("student_name") or profiles.get(view["student"], {}).get("name", view["student"])


def _table(views, profiles):
    return pd.DataFrame([{
        "תאריך": v["date"], "תלמיד": _display_name(v, profiles), "שעות": v["duration"],
        "מחיר לשעה (₪)": v["price_per_hour"], "סכום (₪)": v["total"],
        "תשלום": PAYMENTS.get(v["payment"], v["payment"]),
    } for v in reversed(views)])


def _reset_add(profiles, prefix, previous=None):
    key = st.session_state[prefix + "student"]
    profile = profiles[key]
    values = previous or {}
    st.session_state[prefix + "duration"] = float(values.get("duration", profile["default_duration"]))
    st.session_state[prefix + "rate"] = float(values.get("price_per_hour", profile["default_rate"]))
    payment = values.get("payment", profile["default_payment"])
    st.session_state[prefix + "payment"] = payment if payment in PAYMENTS else "bit"
    st.session_state[prefix + "mode"] = "סכום קבוע" if values.get("mode") == "fixed" or key == "other" else "שעות × מחיר"
    st.session_state[prefix + "fixed"] = float(values.get("total", 100))
    st.session_state[prefix + "name"] = values.get("student_name", "")
    st.session_state[prefix + "defaults_signature"] = (
        key, profile["default_rate"], profile["default_duration"], profile["default_payment"])


def _add_lesson(db, original, state, active, profiles, year, today, now):
    st.subheader("➕ רישום שיעור")
    prefix = f"lesson_add_{year}_"
    include_inactive = st.checkbox("הצג גם תלמידים לא פעילים", key=prefix + "inactive")
    options = [key for key, p in profiles.items() if p["active"] or include_inactive or key == "other"]
    if not options:
        st.info("הוסף תלמיד דרך לשונית התלמידים.")
        return
    if st.session_state.get(prefix + "student") not in options:
        st.session_state[prefix + "student"] = options[0]
        _reset_add(profiles, prefix)
    current = st.session_state[prefix + "student"]
    profile = profiles[current]
    signature = (current, profile["default_rate"], profile["default_duration"], profile["default_payment"])
    if st.session_state.get(prefix + "defaults_signature") != signature:
        _reset_add(profiles, prefix)
    student = st.selectbox("תלמיד", options, format_func=lambda k: profiles[k]["name"],
                           key=prefix + "student", on_change=_reset_add, args=(profiles, prefix))
    previous = sorted((v for v in active if v["student"] == student and v["date"] <= today.isoformat()),
                      key=lambda v: (v["date"], v["_source_index"]))
    if previous:
        last = previous[-1]
        st.button("↩️ מילוי לפי השיעור האחרון", key=prefix + "repeat",
                  on_click=_reset_add, args=(profiles, prefix, last))
        st.caption(f"השיעור האחרון: {last['date']} · ₪{last['total']:,.0f}. מילוי בלבד — נשמר רק באישור למטה.")
    columns = st.columns(3)
    with columns[0]:
        lesson_date = st.date_input("תאריך השיעור", value=today if year == today.year else date(year, 1, 1),
                                    min_value=date(year, 1, 1), max_value=date(year, 12, 31), key=prefix + "date")
    with columns[1]:
        mode = st.radio("שיטת חישוב", ["שעות × מחיר", "סכום קבוע"], key=prefix + "mode", horizontal=True)
    with columns[2]:
        custom_name = st.text_input("שם עבור 'אחר'", disabled=student != "other", key=prefix + "name")
    columns = st.columns(3)
    with columns[0]:
        duration = st.number_input("משך בשעות (45 דקות = 0.75)", min_value=0.0, max_value=10.0,
                                   step=0.25, key=prefix + "duration")
    with columns[1]:
        rate = st.number_input("מחיר לשעה (₪)", min_value=0.0, step=10.0,
                               key=prefix + "rate", disabled=mode == "סכום קבוע")
    with columns[2]:
        fixed = st.number_input("סכום קבוע (₪)", min_value=0.0, step=10.0,
                                key=prefix + "fixed", disabled=mode != "סכום קבוע")
    payment = st.radio("אופן תשלום", list(PAYMENTS), format_func=PAYMENTS.get,
                       horizontal=True, key=prefix + "payment")
    total = fixed if mode == "סכום קבוע" else duration * rate
    st.info(f"לאישור: {custom_name.strip() if student == 'other' and custom_name.strip() else profiles[student]['name']}"
            f" · {lesson_date:%d.%m.%Y} · {duration:g} שעות · ₪{total:,.2f}")
    if lesson_date > today:
        st.caption("זהו שיעור עתידי: הוא יופיע בתכנון, וייכלל בהכנסה בפועל רק בהגיע התאריך.")
    candidate = {"student": student, "student_name": custom_name.strip() if student == "other" else "",
                 "date": lesson_date.isoformat(), "duration": duration, "total": total}
    matches = duplicate_matches(active, candidate)
    allow_duplicate = False
    if matches:
        st.warning("כבר קיים שיעור עם אותו תלמיד, תאריך, משך וסכום. בדוק שלא מדובר בהזנה כפולה.")
        allow_duplicate = st.checkbox("זהו שיעור נוסף ונפרד — שמור בכל זאת", key=prefix + "duplicate")
    if st.button("✅ שמור שיעור", key=prefix + "save", disabled=bool(matches) and not allow_duplicate):
        try:
            record = new_record(student, custom_name, lesson_date.isoformat(), duration, total, payment,
                                "fixed" if mode == "סכום קבוע" else "hours", now)
            _persist(db, original, append_record(state, record))
        except ValueError as error:
            st.error(str(error))


def _records(db, original, state, active, archived, profiles, year, now):
    records = year_views(active, year)
    st.subheader(f"📋 שיעורים — {year}")
    if records:
        frame = _table(records, profiles)
        st.dataframe(frame, hide_index=True, width="stretch")
        st.download_button("הורדת טבלת השנה (CSV)", frame.to_csv(index=False).encode("utf-8-sig"),
                           f"lessons-{year}.csv", "text/csv", key=f"csv_{year}")
        with st.expander("✏️ עריכה והעברה לארכיון"):
            selected = st.selectbox("בחר רשומה לעריכה", list(range(len(records))),
                                    format_func=lambda i: f"{records[i]['date']} · {_display_name(records[i], profiles)} · ₪{records[i]['total']:,.0f}",
                                    key=f"manage_record_{year}")
            view = records[selected]
            prefix = f"edit_{year}_{view['_source_index']}_"
            with st.form(prefix + "form"):
                student_keys = list(profiles)
                student = st.selectbox("שיוך לתלמיד", student_keys, index=student_keys.index(view["student"]),
                                        format_func=lambda k: profiles[k]["name"], key=prefix + "student")
                name = st.text_input("שם תלמיד עבור 'אחר'", value=view.get("student_name", ""), key=prefix + "name")
                new_date = st.date_input("תאריך מתוקן", value=date.fromisoformat(view["date"]),
                                         min_value=date(2000, 1, 1), key=prefix + "date")
                duration = st.number_input("משך מתוקן (שעות)", min_value=0.0, max_value=max(10.0, float(view["duration"])),
                                           value=float(view["duration"]), step=0.25, key=prefix + "duration")
                total = st.number_input("סכום מתוקן (₪)", min_value=0.0, value=float(view["total"]), key=prefix + "total")
                payments = list(PAYMENTS)
                if view["payment"] not in payments:
                    payments.append(view["payment"])
                payment = st.selectbox("תשלום מתוקן", payments, index=payments.index(view["payment"]),
                                        format_func=lambda x: PAYMENTS.get(x, str(x)), key=prefix + "payment")
                duplicate_ok = st.checkbox("אם קיימת רשומה זהה — אני מאשר שזהו שיעור נפרד", key=prefix + "duplicate")
                save = st.form_submit_button("💾 שמור עריכה")
            if save:
                try:
                    values = new_record(student, name, new_date.isoformat(), duration, total,
                                        payment if payment in PAYMENTS else "bit", "fixed", now)
                    # Preserve unrecognized historical payment labels when editing older records.
                    values["payment"] = payment
                    values.pop("created_at")
                    values.pop("id")
                    if duplicate_matches(active, values, view["_source_index"]) and not duplicate_ok:
                        st.error("קיימת רשומה זהה. אשר שמדובר בשיעור נפרד לפני השמירה.")
                    else:
                        _persist(db, original, edit_record(state, view["_source_index"], values, now))
                except ValueError as error:
                    st.error(str(error))
            original_record = state["lessons"][view["_source_index"]]
            if original_record.get("edit_history"):
                st.caption(f"לרשומה {len(original_record['edit_history'])} עריכות קודמות, הכלולות בגיבוי JSON.")
            confirmed = st.checkbox("העבר לארכיון והסר מהסיכומים — ניתן לשחזר", key=prefix + "archive_confirm")
            if st.button("🗄️ העבר לארכיון", key=prefix + "archive", disabled=not confirmed):
                _persist(db, original, archive_record(state, view["_source_index"], now))
    else:
        st.info(f"אין עדיין שיעורים פעילים בשנת {year}. שיעורים משנים קודמות זמינים בבחירת השנה למעלה.")
    archived_records = year_views(archived, year)
    if archived_records:
        with st.expander(f"🗄️ ארכיון {year} — {len(archived_records)} שיעורים"):
            st.dataframe(_table(archived_records, profiles), hide_index=True, width="stretch")
            selected = st.selectbox("רשומה לשחזור", list(range(len(archived_records))),
                                    format_func=lambda i: f"{archived_records[i]['date']} · {_display_name(archived_records[i], profiles)}",
                                    key=f"restore_record_{year}")
            if st.button("↩️ שחזר שיעור", key=f"restore_{year}"):
                _persist(db, original, archive_record(state, archived_records[selected]["_source_index"], now, restore=True))


def _planning(db, original, state, profiles, year, plan, rows, now):
    st.subheader(f"🔮 בפועל מול תכנון — {year}")
    st.caption("התחזית מחברת הכנסה בפועל עד היום עם צפי לימים שנותרו. הטווח השמרני מפחית את הצפי העתידי בלבד.")
    frame = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_bar(x=frame["month"], y=frame["actual"], name="בפועל", marker_color="#42a5f5")
    fig.add_bar(x=frame["month"], y=frame["remaining"], name="צפי להמשך", marker_color="#b0bec5")
    fig.add_scatter(x=frame["month"], y=frame["expected"], name="תכנון חודשי מלא", mode="lines+markers")
    fig.update_layout(barmode="stack", yaxis_title="₪", height=380, legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch", key=f"lesson_forecast_{year}")
    st.dataframe(frame[["month", "count", "hours", "actual", "expected_to_date", "gap", "remaining", "projected"]].rename(columns={
        "month": "חודש", "count": "שיעורים שבוצעו", "hours": "שעות בפועל", "actual": "הכנסה בפועל (₪)",
        "expected_to_date": "תכנון עד היום (₪)", "gap": "פער מול התכנון (₪)",
        "remaining": "צפי להמשך (₪)", "projected": "סה״כ צפוי (₪)"}), hide_index=True, width="stretch")
    st.caption("הפער נמדד מול החלק שכבר חלף בכל חודש, ולא מול חודש מלא. תכנון עבר משקף את ההנחות השמורות, ואינו תקציב שנרשם בהכרח בזמן אמת.")

    annual = []
    for key, profile in profiles.items():
        student_plan = {"students": {key: plan["students"][key]}}
        # An empty history isolates the annual planning assumptions from actual lessons.
        planned = forecast([], student_plan, year, date(year - 1, 12, 31))
        annual.append({"תלמיד": profile["name"], "סוג פעילות": PATTERNS[student_plan["students"][key]["pattern"]],
                       "תכנון שנתי (₪)": round(sum(r["projected"] for r in planned), 2),
                       "עד תאריך": student_plan["students"][key]["end_date"]})
    with st.expander("הנחות לפי תלמיד ועריכת התכנון"):
        st.dataframe(pd.DataFrame(annual), hide_index=True, width="stretch")
        student = st.selectbox("תלמיד לתכנון", list(profiles), format_func=lambda k: profiles[k]["name"], key=f"plan_student_{year}")
        saved = plan["students"][student]
        prefix = f"plan_{year}_{student}_"
        pattern = st.selectbox("תדירות לתכנון", list(PATTERNS), index=list(PATTERNS).index(saved["pattern"]),
                               format_func=PATTERNS.get, key=prefix + "pattern")
        with st.form(prefix + pattern + "form"):
            enabled = st.checkbox("כלול בתחזית", value=saved["enabled"], key=prefix + "enabled")
            columns = st.columns(2)
            with columns[0]:
                rate = st.number_input("תעריף לתחזית (₪ לשעה)", min_value=0.0, value=float(saved["rate"]), key=prefix + "rate")
                duration = st.number_input("משך שיעור לתחזית (שעות)", min_value=0.25, max_value=10.0,
                                           value=float(saved["duration"]), step=0.25, key=prefix + "duration")
                start = st.date_input("תחילת פעילות לתחזית", value=date.fromisoformat(saved["start_date"]), key=prefix + "start")
            with columns[1]:
                frequency = st.number_input("שיעורים בשבוע / בחודש", min_value=0.0, value=float(saved["frequency"]), key=prefix + "frequency")
                weeks = st.number_input("שבועות בתשלום בשנה (לפעילות שבועית)", min_value=0.0, max_value=53.0,
                                        value=float(saved["weeks_per_year"]), key=prefix + "weeks")
                end = st.date_input("סיום פעילות לתחזית", value=date.fromisoformat(saved["end_date"]), key=prefix + "end")
            conservative = st.slider("שיעור מימוש בתרחיש השמרני (%)", 0, 100,
                                     int(round(saved["conservative_factor"] * 100)), key=prefix + "conservative")
            monthly_hours = dict(saved["monthly_hours"])
            include_resits = bool(saved.get("include_resits"))
            resit_hours = float(saved.get("resit_hours", 6))
            if pattern == "seasonal":
                st.caption("ערוך את שעות ההוראה הצפויות בכל חודש. שחר: ינואר–יוני כ־2.33 שעות לחודש, יולי 8 שעות כהנחת תכנון בלבד.")
                hours_frame = pd.DataFrame({"חודש": list(range(1, 13)), "שעות": [float(monthly_hours.get(str(m), 0)) for m in range(1, 13)]})
                edited = st.data_editor(hours_frame, hide_index=True, disabled=["חודש"],
                                        column_config={"שעות": st.column_config.NumberColumn(min_value=0, max_value=300, step=0.25)},
                                        key=prefix + "hours")
                monthly_hours = {str(int(row["חודש"])): float(row["שעות"]) for _, row in edited.iterrows()}
                include_resits = st.checkbox("כלול תוספת מועד ב׳ אפשרית באוגוסט", value=include_resits, key=prefix + "resits")
                resit_hours = st.number_input("שעות נוספות באוגוסט אם יידרש מועד ב׳", min_value=0.0,
                                              value=resit_hours, key=prefix + "resit_hours")
                st.caption("תוספת מועד ב׳ היא אפשרות בלבד: נכללת בתרחיש הבסיס כאשר מסומנת, ואינה נכללת בתרחיש השמרני.")
            save = st.form_submit_button("💾 שמור תכנון לתלמיד ולשנה")
        if save:
            if enabled and (end < start or start.year > year or end.year < year):
                st.error("בחר טווח פעילות תקין שחופף לשנה הנבחרת. כדי להוציא תלמיד מהתחזית, בטל 'כלול בתחזית'.")
            else:
                updated_plan = copy.deepcopy(plan)
                updated_plan["students"][student].update({
                    "enabled": enabled, "pattern": pattern, "rate": rate, "duration": duration,
                    "frequency": frequency, "weeks_per_year": weeks, "start_date": start.isoformat(),
                    "end_date": end.isoformat(), "monthly_hours": monthly_hours,
                    "conservative_factor": conservative / 100, "include_resits": include_resits, "resit_hours": resit_hours,
                })
                _save_plan(db, original, state, year, updated_plan, now)

    with st.expander("🎯 יעד שנתי — אופציונלי"):
        with st.form(f"goal_form_{year}"):
            goal_enabled = st.checkbox("הצג יעד לשנה הנבחרת", value=plan["goal_enabled"], key=f"goal_enabled_{year}")
            amount = st.number_input("סכום היעד (₪)", min_value=1.0, value=float(plan["goal_amount"]), key=f"goal_amount_{year}")
            if st.form_submit_button("שמור הגדרת יעד"):
                updated_plan = copy.deepcopy(plan)
                updated_plan.update(goal_enabled=goal_enabled, goal_amount=amount)
                _save_plan(db, original, state, year, updated_plan, now)
    if plan["goal_enabled"]:
        actual = sum(r["actual"] for r in rows)
        gap = max(float(plan["goal_amount"]) - actual, 0)
        st.progress(min(actual / float(plan["goal_amount"]), 1),
                    text=f"₪{actual:,.0f} מתוך ₪{plan['goal_amount']:,.0f} · נותרו ₪{gap:,.0f}")
        st.caption(f"הפער להכנסה בפועל שקול לכ־{gap / 150:.1f} שעות בתעריף ייחוס של ₪150 לשעה; אינו כולל צפי שטרם התממש.")


def _save_plan(db, original, state, year, plan, now):
    plans = copy.deepcopy(state.get("year_plans", {}))
    previous = copy.deepcopy(plans.get(str(year), {}))
    history = previous.pop("history", [])
    if not isinstance(history, list):
        st.error("היסטוריית התכנון אינה תקינה; לא בוצעה שמירה.")
        return
    plan["history"] = history + [{"saved_at": now, "previous": previous}]
    plans[str(year)] = plan
    _persist(db, original, save_metadata(state, "year_plans", plans))


def _students(db, original, state, profiles, now):
    st.subheader("👥 תלמידים וברירות מחדל")
    st.caption("שינוי תעריף משפיע על הזנות חדשות. סכומים ותעריפים של שיעורים קיימים נשארים כפי שנשמרו. תכנון שכבר נשמר לשנה מסוימת נערך בלשונית התחזית.")
    st.dataframe(pd.DataFrame([{"תלמיד": p["name"], "פעיל": p["active"], "מחיר לשעה (₪)": p["default_rate"],
                                "משך רגיל (שעות)": p["default_duration"],
                                "סכום לשיעור רגיל (₪)": p["default_rate"] * p["default_duration"],
                                "תשלום": PAYMENTS.get(p["default_payment"], p["default_payment"])}
                               for p in profiles.values()]), hide_index=True, width="stretch")
    selected = st.selectbox("עריכת תלמיד או הוספת חדש", ["__new__"] + list(profiles),
                            format_func=lambda k: "➕ תלמיד חדש" if k == "__new__" else profiles[k]["name"],
                            key="student_settings_select")
    profile = profiles.get(selected, {"name": "", "default_rate": 150, "default_duration": 1,
                                      "default_payment": "bit", "active": True,
                                      "start_date": now[:10], "end_date": ""})
    with st.form(f"student_settings_{selected}"):
        name = st.text_input("שם התלמיד/ה", value=profile["name"])
        active = st.checkbox("תלמיד פעיל — מופיע ברישום הרגיל", value=profile["active"])
        rate = st.number_input("מחיר ברירת מחדל לשעה (₪)", min_value=0.0, value=float(profile["default_rate"]))
        duration = st.number_input("משך שיעור רגיל בשעות", min_value=0.25, max_value=10.0,
                                   value=float(profile["default_duration"]), step=0.25)
        payments = list(PAYMENTS)
        payment = st.selectbox("תשלום ברירת מחדל", payments,
                                index=payments.index(profile["default_payment"]) if profile["default_payment"] in payments else 0,
                                format_func=PAYMENTS.get)
        start = st.date_input("תאריך התחלת פעילות", value=date.fromisoformat(profile["start_date"]))
        has_end = st.checkbox("יש מועד סיום צפוי", value=bool(profile["end_date"]))
        end = st.date_input("תאריך סיום צפוי", value=date.fromisoformat(profile["end_date"] or f"{start.year}-12-31"))
        st.caption("איתי ואדווה: 45 דקות = 0.75 שעה, בתעריף ₪160 לשעה — סכום של ₪120 לשיעור.")
        save = st.form_submit_button("💾 שמור תלמיד")
    if save:
        if not name.strip() or (has_end and end < start):
            st.error("יש להזין שם וטווח תאריכים תקין.")
        elif any(p["name"].strip() == name.strip() and key != selected for key, p in profiles.items()):
            st.error("כבר קיים תלמיד בשם הזה. בחר אותו לעריכה.")
        else:
            key = selected if selected != "__new__" else "student_" + uuid.uuid4().hex[:12]
            stored = copy.deepcopy(state.get("student_profiles", {}))
            saved_profile = copy.deepcopy(profile)
            history = saved_profile.pop("history", [])
            if not isinstance(history, list):
                st.error("היסטוריית התלמיד אינה תקינה; לא בוצעה שמירה.")
                return
            previous = copy.deepcopy(saved_profile)
            saved_profile.update(name=name.strip(), active=active, default_rate=rate, default_duration=duration,
                                 default_payment=payment, start_date=start.isoformat(), end_date=end.isoformat() if has_end else "")
            saved_profile.setdefault("pattern", "weekly")
            saved_profile["history"] = history + [{"saved_at": now, "previous": previous}]
            stored[key] = saved_profile
            _persist(db, original, save_metadata(state, "student_profiles", stored))


def render_lessons_dashboard(db, normalize_record, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Jerusalem")).date()
    now = datetime.now(ZoneInfo("Asia/Jerusalem")).isoformat(timespec="seconds")
    st.title("📚 שיעורים פרטיים")
    st.caption("הכנסות, תלמידים ותכנון לפי שנה. מעבר שנה אינו מוחק או מעביר שיעורים; כל השנים נשארות נגישות כאן.")
    if st.session_state.get("lessons_saved_notice"):
        st.success(st.session_state.pop("lessons_saved_notice"))
    original = db.get_lessons_data({"_read_failed": True})
    try:
        state = lesson_state(original)
        active, archived, invalid = [], [], []
        for index, record in enumerate(state["lessons"]):
            view, error = normalize_record(record, index)
            if error:
                invalid.append({"רשומה": index + 1, "שגיאה": error})
            elif view["_archived"]:
                archived.append(view)
            else:
                active.append(view)
        profiles = student_profiles(state, active + archived)
        years = available_years(active + archived, today, state.get("year_plans"))
        year = st.selectbox("שנת פעילות", years, index=years.index(today.year), key=f"lessons_year_{today.year}")
        plan = year_plan(state, profiles, year)
        rows = forecast(active, plan, year, today)
    except (ValueError, TypeError, KeyError) as error:
        st.error(f"לא ניתן לפתוח את הנתונים בבטחה: {error}")
        return
    if year < today.year:
        st.info(f"אתה צופה בשנת {year}. ניתן לעיין, לייצא ולתקן רשומות; כל שינוי שומר היסטוריה.")
    elif year > today.year:
        st.info(f"תכנון מוקדם לשנת {year}. ההכנסות מתחילות מאפס; נתוני השנים הקודמות נשמרים בנפרד בתצוגה.")
    if invalid:
        st.warning(f"{len(invalid)} רשומות לא תקינות נשארו שמורות ונכללות בגיבוי המלא, אך לא בחישובים.")
        with st.expander("רשומות לבדיקה"):
            st.dataframe(pd.DataFrame(invalid), hide_index=True)
    actual = sum(r["actual"] for r in rows)
    projected = sum(r["projected"] for r in rows)
    low = sum(r["conservative"] for r in rows)
    columns = st.columns(4)
    columns[0].metric(f"הכנסות בפועל — {year}", f"₪{actual:,.0f}")
    columns[1].metric("שיעורים שבוצעו", str(sum(r["count"] for r in rows)))
    columns[2].metric("שעות הוראה", f"{sum(r['hours'] for r in rows):,.2f}")
    columns[3].metric("תחזית לסיום השנה" if year >= today.year else "סיכום שנה", f"₪{projected:,.0f}")
    if year >= today.year:
        st.caption(f"טווח שמרני–בסיס: ₪{low:,.0f}–₪{projected:,.0f}. התחזית היא הנחה ניתנת לעריכה ואינה הכנסה שהתקבלה.")
    if sum(r["scheduled"] for r in rows):
        st.caption("שיעורים שהוזנו לתאריכים עתידיים מוצגים בצפי בלבד. בכל תלמיד וחודש הם מחליפים את הצפי אם סכומם גבוה ממנו, ואינם נספרים פעמיים.")
    with st.expander("💾 גיבוי והורדת נתונים"):
        st.download_button(f"גיבוי שנתי מלא — {year} (JSON)",
                           json.dumps(year_export(state, year, plan, now), ensure_ascii=False, indent=2),
                           f"lessons-{year}-backup.json", "application/json", key=f"backup_year_{year}")
        st.download_button("גיבוי כל השנים וכל ההיסטוריה (JSON)",
                           json.dumps(state, ensure_ascii=False, indent=2),
                           f"lessons-all-years-{today}.json", "application/json", key="backup_all_lessons")
        st.caption("הגיבוי השנתי כולל שיעורים בארכיון והיסטוריית עריכות. הגיבוי המלא כולל גם רשומות לא תקינות וכל ההגדרות.")
    records_tab, planning_tab, students_tab = st.tabs(["📝 שיעורים וסיכומים", "🔮 תחזית ותכנון", "👥 תלמידים והגדרות"])
    with records_tab:
        _add_lesson(db, original, state, active, profiles, year, today, now)
        st.divider()
        completed = [v for v in year_views(active, year) if v["date"] <= today.isoformat()]
        if completed:
            grouped = []
            for key, profile in profiles.items():
                records = [v for v in completed if v["student"] == key]
                if not records:
                    continue
                hours = sum(v["duration"] for v in records)
                timed_income = sum(v["total"] for v in records if v["duration"] > 0)
                grouped.append({"תלמיד": profile["name"], "שיעורים": len(records), "שעות": hours,
                                "הכנסה (₪)": sum(v["total"] for v in records),
                                "ממוצע לשעה (₪)": round(timed_income / hours, 2) if hours else None})
            st.subheader("📊 סיכום לפי תלמיד")
            st.dataframe(pd.DataFrame(grouped), hide_index=True, width="stretch")
        _records(db, original, state, active, archived, profiles, year, now)
    with planning_tab:
        _planning(db, original, state, profiles, year, plan, rows, now)
    with students_tab:
        _students(db, original, state, profiles, now)
