"""Read-only investment calculator. Fragment reruns never execute portfolio trades."""
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from investment_projection import compare_funding, project_investment


FUNDING_LABELS = {"baseline": "המשך כמו היום", "monthly_only": "שינוי חודשי בלבד",
                  "lumps_only": "הפקדות חד־פעמיות בלבד", "combined": "התרחיש שלך — הכל יחד"}


def _reset_monthly(average):
    st.session_state["projection_monthly"] = float(average)


@st.fragment
def render_investment_projection(current_value_usd, invested_value_usd, monthly_stats,
                                 usd_to_ils, as_of):
    st.subheader("🔮 מחשבון השקעות עתידי")
    st.caption("השווה בין המשך ההפקדות הנוכחיות לתרחיש שלך. השינויים כאן הם לסימולציה בלבד ואינם רושמים הפקדה, רכישה או מכירה בתיק.")
    if not all(math.isfinite(float(v)) for v in (current_value_usd, invested_value_usd, monthly_stats["average"])):
        st.error("לא התקבלו נתוני בסיס תקינים למחשבון. רענן את נתוני התיק.")
        return
    average = max(float(monthly_stats["average"]), 0)
    source_columns = st.columns(3)
    source_columns[0].metric("שווי התיק הנוכחי ($)", f"${current_value_usd:,.2f}")
    source_columns[1].metric("שווי ההשקעות ללא מזומן ($)", f"${invested_value_usd:,.2f}")
    source_columns[2].metric("ממוצע הפקדות חודשי שמור ($)", f"${average:,.2f}")
    st.caption(f"הבסיס נלקח מנתוני התיק שנטענו ב־{as_of}. הממוצע מחושב מההפקדות הדולריות השמורות לאורך {monthly_stats['months']} חודשים, כולל חודשים ללא הפקדה; רכישות ומכירות מתוך התיק אינן הפקדות חדשות.")
    include_cash = st.radio("סכום התחלתי לחישוב", ["כל התיק, כולל מזומן", "השקעות בלבד, ללא מזומן"],
                            horizontal=True, key="projection_start_source") == "כל התיק, כולל מזומן"
    initial = float(current_value_usd if include_cash else invested_value_usd)
    if initial < 0:
        st.error("השווי ההתחלתי שלילי; יש לבדוק את יתרת התיק לפני חישוב תחזית.")
        return
    if include_cash:
        st.caption("בבחירה זו המודל מניח שכל הסכום, כולל המזומן הנוכחי, יושקע ויצבור את התשואה שבחרת.")
    columns = st.columns(3)
    with columns[0]:
        years = st.slider("תקופת השקעה בשנים", 1, 50, 20, key="projection_years")
    with columns[1]:
        focus_rate = st.number_input("תשואה שנתית להשוואה (%)", min_value=-99.0, max_value=50.0,
                                     value=7.0, step=0.5, key="projection_focus_rate")
    with columns[2]:
        currency = st.selectbox("מטבע תצוגת התוצאות", ["USD", "ILS"],
                                format_func=lambda c: "דולר ($)" if c == "USD" else "שקל (₪)",
                                key="projection_currency")
    months = int(years) * 12
    factor = float(usd_to_ils) if currency == "ILS" else 1.0
    if not math.isfinite(factor) or factor <= 0:
        st.error("שער ההמרה אינו תקין. בחר תצוגה בדולרים או רענן את התיק.")
        return
    symbol = "₪" if currency == "ILS" else "$"
    money = lambda v: f"{symbol}{v * factor:,.0f}"
    if currency == "ILS":
        st.caption(f"התוצאות מומרות בשער הנוכחי: ₪{usd_to_ils:.4f} לדולר. זו המרה לתצוגה, ללא תחזית לשינוי בשער המטבע. סכומי ההפקדה מוזנים בדולרים.")

    st.markdown("**שינוי ההפקדות בתרחיש שלך**")
    st.button("↩️ אפס את ההפקדה החודשית לממוצע השמור", key="projection_reset_monthly",
              on_click=_reset_monthly, args=(average,))
    columns = st.columns(2)
    with columns[0]:
        changed_monthly = st.number_input("הפקדה חודשית בתרחיש שלך ($)", min_value=0.0,
                                          value=average, step=100.0, key="projection_monthly")
    with columns[1]:
        if st.session_state.get("projection_change_after", 0) > months:
            st.session_state["projection_change_after"] = months
        change_after = st.number_input("השינוי יתחיל בעוד כמה חודשים?", min_value=0, max_value=months,
                                       value=0, step=1, key="projection_change_after",
                                       help="0 = מההפקדה הקרובה. 12 = שנה בקצב הנוכחי, ואז ההפקדה החדשה.")
    lumps = []
    if st.checkbox("הוסף הפקדות חד־פעמיות", key="projection_use_lumps"):
        st.caption("אפשר להוסיף כמה שורות. חודש 0 = הפקדה כעת; חודש 12 = בסוף השנה הראשונה. הסכומים הם כסף חדש מעבר לשווי התיק הקיים.")
        editor = st.data_editor(pd.DataFrame({"בעוד חודשים": [0], "סכום ($)": [0.0]}),
                                num_rows="dynamic", hide_index=True, width="stretch",
                                column_config={
                                    "בעוד חודשים": st.column_config.NumberColumn(min_value=0, max_value=600, step=1, required=True),
                                    "סכום ($)": st.column_config.NumberColumn(min_value=0, step=100, required=True),
                                }, key="projection_lump_editor")
        for _, row in editor.iterrows():
            if pd.isna(row["סכום ($)"]) or pd.isna(row["בעוד חודשים"]):
                st.error("השלם סכום וחודש בכל שורת הפקדה, או הסר שורות ריקות.")
                return
            if float(row["סכום ($)"]) > 0:
                lumps.append({"month": row["בעוד חודשים"], "amount": row["סכום ($)"]})

    rates = st.multiselect("תשואות שנתיות נוספות להשוואה (%)", [-5.0, 0.0, 3.0, 5.0, 7.0, 9.0, 12.0],
                           default=[0.0, 3.0, 5.0, 9.0], key="projection_comparison_rates",
                           help="התשואה בשדה ההשוואה הראשי נכללת תמיד. אלו הנחות לבדיקה, ולא תחזית לתשואת השוק.")
    inflation = 0.0
    with st.expander("הנחות חישוב וכוח קנייה"):
        adjust_inflation = st.checkbox("הצג גם שווי בכוח הקנייה של היום", key="projection_adjust_inflation")
        if adjust_inflation:
            inflation = st.number_input("הנחת אינפלציה שנתית (%)", min_value=0.0, max_value=30.0,
                                         value=2.0, step=0.5, key="projection_inflation")
        st.caption("התשואה השנתית מומרת לתשואה חודשית שקולה בריבית דריבית. ההפקדות החודשיות והפקדות עתידיות מתווספות בסוף החודש; הפקדה בחודש 0 מושקעת מיד. התשואה מניחה השקעה מחדש של חלוקות, ללא חישוב נוסף ונפרד לדיבידנדים. אין ניכוי מסים או עמלות. התשואה קבועה במודל; בפועל היא משתנה והתוצאות אינן מובטחות.")
        st.markdown("[הסבר ומחשבון ריבית דריבית — Investor.gov](https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator)")
    try:
        comparisons = compare_funding(initial, average, months, focus_rate, changed_monthly,
                                       int(change_after), lumps, inflation)
        paths = {rate: project_investment(initial, average, months, rate, changed_monthly,
                                         int(change_after), lumps, inflation)
                 for rate in sorted(set(rates + [float(focus_rate)]))}
    except (ValueError, TypeError) as error:
        st.error(f"בדוק את נתוני הסימולציה: {error}")
        return

    baseline = comparisons["baseline"][-1]
    combined = comparisons["combined"][-1]
    delta = combined["balance"] - baseline["balance"]
    columns = st.columns(4)
    columns[0].metric(f"המשך כמו היום — בעוד {years} שנים", money(baseline["balance"]))
    columns[1].metric("התרחיש שלך — שווי עתידי", money(combined["balance"]))
    columns[2].metric("השפעת השינויים על השווי", money(delta))
    columns[3].metric("רווח חזוי מהיום בתרחיש שלך", money(combined["growth"]))
    st.caption(f"ההשוואה כאן בתשואה שנתית של {focus_rate:g}%. מתוך השינוי בשווי: {money(combined['future_deposits'] - baseline['future_deposits'])} שינוי בהפקדות, ו־{money(combined['growth'] - baseline['growth'])} שינוי ברווח המצטבר.")
    if adjust_inflation:
        st.info(f"בהנחת אינפלציה של {inflation:g}%: השווי בתרחיש שלך שקול לכ־{money(combined['real_value'])} בכוח הקנייה של היום.")

    fig = go.Figure()
    for rate, path in paths.items():
        fig.add_scatter(x=[r["years"] for r in path], y=[r["balance"] * factor for r in path],
                        name=f"התרחיש שלך · {rate:g}%", mode="lines",
                        line=dict(width=3 if rate == focus_rate else 1.5))
    fig.add_scatter(x=[r["years"] for r in comparisons["baseline"]],
                    y=[r["balance"] * factor for r in comparisons["baseline"]],
                    name=f"המשך כמו היום · {focus_rate:g}%", mode="lines", line=dict(dash="dash", width=3, color="#64748b"))
    fig.update_layout(xaxis_title="שנים מהיום", yaxis_title=f"שווי תיק ({symbol})", height=430,
                      hovermode="x unified", legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, width="stretch", key="projection_return_chart")

    st.markdown("**מה יוצר את ההבדל?**")
    funding_rows = []
    for key, path in comparisons.items():
        final = path[-1]
        funding_rows.append({"תרחיש": FUNDING_LABELS[key],
                             "הפקדות חדשות": final["future_deposits"] * factor,
                             "רווח מהיום": final["growth"] * factor,
                             "שווי עתידי": final["balance"] * factor,
                             "פער לעומת ההמשך הנוכחי": (final["balance"] - baseline["balance"]) * factor})
    money_column = lambda: st.column_config.NumberColumn(format=f"{symbol}%.0f")
    st.dataframe(pd.DataFrame(funding_rows), hide_index=True, width="stretch",
                  column_config={name: money_column() for name in funding_rows[0] if name != "תרחיש"})

    with st.expander("תוצאות לכל תשואה, פירוט שנתי והורדה"):
        result_rows = []
        for rate, path in paths.items():
            final = path[-1]
            row = {"תשואה שנתית (%)": rate, "סכום התחלתי": initial * factor,
                   "הפקדות חדשות": final["future_deposits"] * factor,
                   "רווח מהיום": final["growth"] * factor, "שווי עתידי": final["balance"] * factor}
            if adjust_inflation:
                row["שווי בכוח הקנייה של היום"] = final["real_value"] * factor
            result_rows.append(row)
        st.dataframe(pd.DataFrame(result_rows), hide_index=True, width="stretch")
        annual_rows = [{"שנים מהיום": r["years"], "סכום התחלתי": initial * factor,
                        "הפקדות חדשות": r["future_deposits"] * factor, "רווח מהיום": r["growth"] * factor,
                        "שווי עתידי": r["balance"] * factor, "שווי בכוח הקנייה של היום": r["real_value"] * factor}
                       for r in comparisons["combined"] if r["month"] % 12 == 0]
        annual_frame = pd.DataFrame(annual_rows)
        st.dataframe(annual_frame, hide_index=True, width="stretch")
        st.download_button("הורד פירוט שנתי (CSV)", annual_frame.to_csv(index=False).encode("utf-8-sig"),
                           f"investment-projection-{years}y-{focus_rate:g}pct-{currency}.csv", "text/csv",
                           key="projection_download")
