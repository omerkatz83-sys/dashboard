"""Interactive, read-only investment planning. Account operations stay outside the fragment."""
from html import escape
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from investment_projection import compare_funding, project_investment


FUNDING_LABELS = {"baseline": "המשך כמו היום", "monthly_only": "שינוי חודשי בלבד",
                  "lumps_only": "הפקדות חד־פעמיות בלבד", "combined": "התרחיש שלך — הכל יחד"}
TEAL, INDIGO, MUTED = "#089c8a", "#6366f1", "#8b97ad"
STYLE = """
<style>
.st-key-projection_shell {direction:rtl; text-align:right;}
.st-key-projection_shell h3, .st-key-projection_shell h4 {letter-spacing:-.025em;}
.st-key-projection_shell [data-testid="stWidgetLabel"] {text-align:right;}
.st-key-projection_shell [data-testid="stMetric"] {text-align:right;}
.st-key-projection_shell [data-testid="stMetricValue"] {direction:ltr; text-align:right; font-variant-numeric:tabular-nums; font-size:clamp(1.45rem,2.4vw,2.35rem); letter-spacing:-.04em;}
.st-key-projection_shell input[type="number"] {direction:ltr; text-align:left; font-variant-numeric:tabular-nums;}
.st-key-projection_shell .projection-hero {background:linear-gradient(115deg,#12223a,#163e49); color:#fff; border-radius:22px; padding:26px 30px; margin:4px 0 20px; border:1px solid #234d57;}
.st-key-projection_shell .projection-hero h2 {color:#fff; padding:5px 0 8px; font-size:clamp(1.7rem,3vw,2.4rem); font-weight:750; letter-spacing:-.04em;}
.st-key-projection_shell .projection-hero p {margin:0; color:#d2e2e9; font-size:.98rem; line-height:1.65;}
.st-key-projection_shell .projection-eyebrow {font-size:.73rem; letter-spacing:.12em; color:#7de3d0; font-weight:700;}
.st-key-projection_shell .projection-update {display:inline-block; margin-top:15px; padding:5px 10px; border:1px solid #3a5b65; border-radius:30px; color:#c7d9e2; font-size:.73rem;}
.st-key-projection_source [data-testid="stMetric"] {padding:12px 18px; border:1px solid rgba(140,155,180,.2); border-radius:16px;}
.st-key-projection_source [data-testid="stMetricValue"] {font-size:1.45rem;}
.st-key-projection_controls {border-radius:20px; padding:20px!important; border-color:rgba(140,155,180,.24)!important;}
.st-key-projection_results {border-radius:20px; padding:22px!important; border-color:rgba(140,155,180,.24)!important;}
.st-key-projection_shell .projection-section {color:#7b879b; font-size:.73rem; font-weight:700; letter-spacing:.06em; margin:2px 0 10px;}
.st-key-projection_shell .projection-impact {border-radius:12px; padding:12px 16px; margin:6px 0 15px; background:rgba(8,156,138,.09); border:1px solid rgba(8,156,138,.2); line-height:1.7;}
.st-key-projection_shell .projection-impact.negative {background:rgba(217,92,111,.08); border-color:rgba(217,92,111,.2);}
.st-key-projection_shell .projection-impact.neutral {background:rgba(99,102,241,.06); border-color:rgba(99,102,241,.15);}
.st-key-projection_shell .projection-impact strong {font-weight:750;}
.st-key-projection_shell [data-testid="stButton"] button {border-radius:10px; font-size:.86rem; min-height:2.3rem;}
.st-key-projection_shell [data-testid="stButton"] button:hover {border-color:#089c8a; color:#089c8a;}
.st-key-projection_shell [data-testid="stTabs"] [role="tab"] {font-size:.9rem;}
@media(min-width:850px) {.st-key-projection_workspace > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {flex-direction:row-reverse;}}
@media(max-width:850px) {.st-key-projection_shell .projection-hero {padding:20px;} .st-key-projection_controls,.st-key-projection_results {padding:14px!important;}}
</style>
"""


def _set_monthly(amount):
    value = float(amount)
    st.session_state["projection_monthly"] = value
    st.session_state["projection_monthly_slider"] = value


def _sync_monthly(source):
    _set_monthly(st.session_state[source])


def _set_years(years):
    st.session_state["projection_years"] = int(years)


def _reset_scenario(average):
    for key in list(st.session_state):
        if key.startswith("projection_"):
            del st.session_state[key]
    _set_monthly(average)


def _add_lump():
    rows = st.session_state.get("projection_lump_rows", [])
    next_id = st.session_state.get("projection_next_lump_id", 1)
    st.session_state["projection_lump_rows"] = rows + [{"id": next_id, "month": 0, "amount": 0.0}]
    st.session_state["projection_next_lump_id"] = next_id + 1


def _remove_lump(row_id):
    st.session_state["projection_lump_rows"] = [row for row in st.session_state.get("projection_lump_rows", [])
                                                if row["id"] != row_id]


def _lump_controls():
    lumps = []
    if not st.checkbox("הוסף הפקדות חד־פעמיות", key="projection_use_lumps"):
        return lumps
    st.caption("כסף חדש מעבר לתיק הקיים. חודש 0 = עכשיו; חודש 12 = בעוד שנה.")
    if "projection_lump_rows" not in st.session_state:
        st.session_state["projection_lump_rows"] = [{"id": 0, "month": 0, "amount": 0.0}]
    for position, row in enumerate(st.session_state["projection_lump_rows"]):
        with st.container(border=True):
            st.markdown(f"**הפקדה {position + 1}**")
            amount_col, month_col = st.columns([1.3, 1])
            with amount_col:
                amount = st.number_input("סכום ($)", min_value=0.0, value=float(row["amount"]), step=1000.0,
                                          key=f"projection_lump_{row['id']}_amount")
            with month_col:
                month = st.number_input("בעוד חודשים", min_value=0, max_value=600, value=int(row["month"]),
                                         step=1, key=f"projection_lump_{row['id']}_month")
            row["amount"], row["month"] = amount, month
            when = "מושקע מיד" if month == 0 else f"מושקע בסוף חודש {month}"
            st.caption(f"${amount:,.0f} · {when}")
            st.button("הסר הפקדה זו", key=f"projection_lump_{row['id']}_remove",
                      on_click=_remove_lump, args=(row["id"],))
            if amount > 0:
                lumps.append({"month": month, "amount": amount})
    st.button("＋ הוסף הפקדה נוספת", key="projection_add_lump", on_click=_add_lump, width="stretch")
    return lumps


def _chart_layout(fig, symbol, height=380):
    fig.update_layout(height=height, margin=dict(l=12, r=20, t=20, b=15),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Arial, sans-serif", size=12),
                      xaxis=dict(title="שנים מהיום", showgrid=False, zeroline=False),
                      yaxis=dict(title=f"שווי ({symbol})", gridcolor="rgba(140,155,180,.14)", zeroline=False),
                      hovermode="x unified", hoverlabel=dict(font_size=13),
                      legend=dict(orientation="h", y=1.13, x=1, xanchor="right"))
    return fig


def _comparison_chart(comparisons, factor, symbol, inspect_year, show_capital):
    baseline, combined = comparisons["baseline"], comparisons["combined"]
    fig = go.Figure()
    fig.add_scatter(x=[r["years"] for r in baseline], y=[r["balance"] * factor for r in baseline],
                    name="המשך כמו היום", mode="lines", line=dict(color=MUTED, dash="dash", width=2.5))
    fig.add_scatter(x=[r["years"] for r in combined], y=[r["balance"] * factor for r in combined],
                    name="התרחיש שלך", mode="lines", line=dict(color=TEAL, width=3.5),
                    fill="tonexty", fillcolor="rgba(8,156,138,.08)")
    if show_capital:
        fig.add_scatter(x=[r["years"] for r in combined], y=[r["capital"] * factor for r in combined],
                        name="הון התחלתי + הפקדות", mode="lines", line=dict(color=INDIGO, dash="dot", width=1.5))
    fig.add_vline(x=inspect_year, line_width=1, line_dash="dot", line_color="rgba(140,155,180,.55)")
    fig.update_traces(hovertemplate=f"{symbol}%{{y:,.0f}}<extra>%{{fullData.name}}</extra>")
    return _chart_layout(fig, symbol)


def _controls(current_value, invested_value, average):
    st.markdown('<div class="projection-section">01 · בונים תרחיש</div>', unsafe_allow_html=True)
    st.markdown("### מה תרצה לבדוק?")
    st.caption("כל שינוי מעדכן מיד את התוצאה.")
    years = st.slider("תקופת השקעה בשנים", 1, 50, 20, key="projection_years")
    shortcuts = st.columns(4)
    for column, value in zip(shortcuts, (5, 10, 20, 30)):
        column.button(f"{value} שנים", key=f"projection_years_{value}",
                      on_click=_set_years, args=(value,), width="stretch")
    focus_rate = st.number_input("תשואה שנתית להשוואה (%)", min_value=-99.0, max_value=50.0,
                                 value=7.0, step=0.5, key="projection_focus_rate")
    st.divider()
    st.markdown("**כמה תפקיד בכל חודש?**")
    if "projection_monthly" not in st.session_state:
        _set_monthly(average)
    changed = st.number_input("הפקדה חודשית בתרחיש שלך ($)", min_value=0.0, step=100.0,
                              key="projection_monthly", on_change=_sync_monthly, args=("projection_monthly",))
    slider_max = float(max(5000, math.ceil(max(average * 3, changed) / 1000) * 1000))
    st.slider("שינוי מהיר של ההפקדה ($)", 0.0, slider_max, step=50.0,
               key="projection_monthly_slider", on_change=_sync_monthly, args=("projection_monthly_slider",))
    shortcuts = st.columns(3)
    for column, label, value in zip(shortcuts, ("כמו היום", "+ $250", "+ $500"), (average, average + 250, average + 500)):
        column.button(label, key=f"projection_preset_{int(value * 100)}", on_click=_set_monthly,
                      args=(value,), width="stretch")
    st.caption(f"המשך כמו היום: ${average:,.2f} בחודש. השינוי שלך: ${changed - average:+,.2f} בחודש.")
    months = int(years) * 12
    with st.expander("מתי ההפקדה החודשית תשתנה?"):
        if st.session_state.get("projection_change_after", 0) > months:
            st.session_state["projection_change_after"] = months
        change_after = st.number_input("השינוי יתחיל בעוד כמה חודשים?", min_value=0, max_value=months,
                                       value=0, step=1, key="projection_change_after")
        st.caption("0 = מההפקדה הקרובה. 12 = שנה בקצב הקיים, ואז ההפקדה החדשה.")
    st.divider()
    lumps = _lump_controls()
    with st.expander("סכום התחלתי, מטבע והנחות"):
        include_cash = st.radio("סכום התחלתי לחישוב", ["כל התיק, כולל מזומן", "השקעות בלבד, ללא מזומן"],
                                key="projection_start_source") == "כל התיק, כולל מזומן"
        initial = float(current_value if include_cash else invested_value)
        st.caption("כולל מזומן: מניחים שגם המזומן הקיים מושקע וצובר את התשואה שבחרת.")
        currency = st.selectbox("מטבע תצוגת התוצאות", ["USD", "ILS"],
                                format_func=lambda c: "דולר ($)" if c == "USD" else "שקל (₪)", key="projection_currency")
        adjust_inflation = st.checkbox("הצג גם שווי בכוח הקנייה של היום", key="projection_adjust_inflation")
        inflation = st.number_input("הנחת אינפלציה שנתית (%)", min_value=0.0, max_value=30.0,
                                     value=2.0, step=0.5, key="projection_inflation") if adjust_inflation else 0.0
        st.caption("תשואה שנתית קבועה, בריבית דריבית חודשית שקולה. הפקדות בסוף החודש; חודש 0 מושקע מיד. חלוקות מושקעות מחדש, ללא תוספת נפרדת לדיבידנדים. ללא ניכוי מסים או עמלות. אלו תרחישים לבדיקה, לא תשואה מובטחת.")
        st.markdown("[על ריבית דריבית — Investor.gov](https://www.investor.gov/financial-tools-calculators/calculators/compound-interest-calculator)")
    st.button("↩️ חזור להפקדה הממוצעת", key="projection_reset_monthly", on_click=_set_monthly, args=(average,), width="stretch")
    st.button("אפס את כל התרחיש", key="projection_reset_all", on_click=_reset_scenario, args=(average,), width="stretch")
    return years, focus_rate, changed, int(change_after), lumps, initial, currency, adjust_inflation, inflation


def _results(years, focus_rate, initial, average, changed, change_after, lumps, inflation,
             adjust_inflation, factor, symbol):
    try:
        comparisons = compare_funding(initial, average, years * 12, focus_rate, changed, change_after, lumps, inflation)
    except (ValueError, TypeError) as error:
        st.error(f"בדוק את נתוני הסימולציה: {error}")
        return
    money = lambda value: f"{symbol}{value * factor:,.0f}"
    baseline, combined = comparisons["baseline"][-1], comparisons["combined"][-1]
    delta = combined["balance"] - baseline["balance"]
    st.markdown('<div class="projection-section">02 · רואים את ההשפעה</div>', unsafe_allow_html=True)
    st.markdown(f"### התיק שלך בעוד {years} שנים")
    st.caption(f"תשואה שנתית בתרחיש: {focus_rate:g}% · סכום התחלתי: {money(initial)}")
    left, right = st.columns(2)
    right.metric("התרחיש שלך — שווי עתידי", money(combined["balance"]))
    left.metric(f"המשך כמו היום — בעוד {years} שנים", money(baseline["balance"]))
    impact_class = "negative" if delta < -0.01 else "neutral" if abs(delta) <= 0.01 else ""
    impact_text = "התרחישים זהים כרגע. שנה הפקדה חודשית או הוסף סכום חד־פעמי כדי לראות את ההבדל." if abs(delta) <= 0.01 else (
        f"השינויים שלך {'מוסיפים' if delta > 0 else 'מפחיתים'} <strong>{escape(money(abs(delta)))}</strong> מהשווי העתידי, ביחס להמשך בקצב הנוכחי.")
    st.markdown(f'<div class="projection-impact {impact_class}">{impact_text}</div>', unsafe_allow_html=True)
    columns = st.columns(3)
    columns[0].metric("השפעת השינויים על השווי", money(delta))
    columns[1].metric("הפקדות חדשות בתרחיש שלך", money(combined["future_deposits"]))
    columns[2].metric("רווח חזוי מהיום בתרחיש שלך", money(combined["growth"]))
    if adjust_inflation:
        st.info(f"בהנחת אינפלציה של {inflation:g}%: כ־{money(combined['real_value'])} בכוח הקנייה של היום.")
    growth_tab, rates_tab, components_tab = st.tabs(["📈 התקדמות התיק", "↔ השוואת תשואות", "◫ ממה בנויה התוצאה"])
    with growth_tab:
        if st.session_state.get("projection_inspect_year", years) > years:
            st.session_state["projection_inspect_year"] = years
        inspect_year = st.slider("בדוק את התיק בנקודת זמן", 0, int(years), int(years), key="projection_inspect_year")
        show_capital = st.checkbox("הצג גם הון התחלתי והפקדות, ללא רווח", key="projection_show_capital")
        st.plotly_chart(_comparison_chart(comparisons, factor, symbol, inspect_year, show_capital),
                        width="stretch", key="projection_return_chart", config={"displayModeBar": False})
        point, base_point = comparisons["combined"][inspect_year * 12], comparisons["baseline"][inspect_year * 12]
        st.caption(f"בנקודה שנבחרה — בעוד {inspect_year} שנים: התרחיש שלך {money(point['balance'])} · המשך כמו היום {money(base_point['balance'])} · פער {money(point['balance'] - base_point['balance'])}. אפשר לרחף על הקווים לפירוט וללחוץ על המקרא כדי להסתיר קו.")
    with rates_tab:
        rates = st.multiselect("תשואות שנתיות נוספות להשוואה (%)", [-5.0, 0.0, 3.0, 5.0, 7.0, 9.0, 12.0],
                               default=[3.0, 5.0, 9.0], key="projection_comparison_rates")
        st.caption("אותן הפקדות ואותה תקופה, בהנחות תשואה שונות. אלו אינן הסתברויות או תחזית לתשואת השוק.")
        paths = {rate: project_investment(initial, average, years * 12, rate, changed, change_after, lumps, inflation)
                 for rate in sorted(set(rates + [float(focus_rate)]))}
        fig = go.Figure()
        palette = ["#8b97ad", "#818cf8", "#6366f1", "#0d9488", "#0ea5e9", "#c084fc", "#e2a760", "#e76f8a"]
        for index, (rate, path) in enumerate(paths.items()):
            fig.add_scatter(x=[r["years"] for r in path], y=[r["balance"] * factor for r in path],
                            name=f"{rate:g}% לשנה", mode="lines",
                            line=dict(color=TEAL if rate == focus_rate else palette[index % len(palette)], width=3.5 if rate == focus_rate else 1.7))
        st.plotly_chart(_chart_layout(fig, symbol), width="stretch", key="projection_rates_chart", config={"displayModeBar": False})
        result_rows = [{"תשואה שנתית (%)": rate, "שווי עתידי": money(path[-1]["balance"]),
                        "רווח מהיום": money(path[-1]["growth"])} for rate, path in paths.items()]
        st.dataframe(pd.DataFrame(result_rows), hide_index=True, width="stretch")
    with components_tab:
        fig = go.Figure(go.Waterfall(x=["שווי התחלתי", "הפקדות חדשות", "רווח / הפסד", "שווי עתידי"],
                                     measure=["absolute", "relative", "relative", "total"],
                                     y=[initial * factor, combined["future_deposits"] * factor, combined["growth"] * factor, 0],
                                     increasing=dict(marker_color=TEAL), decreasing=dict(marker_color="#dc6b7b"),
                                     totals=dict(marker_color=INDIGO), connector=dict(line_color="rgba(140,155,180,.3)")))
        _chart_layout(fig, symbol, 310).update_xaxes(title=None)
        st.plotly_chart(fig, width="stretch", key="projection_composition_chart", config={"displayModeBar": False})
        st.caption(f"מתוך הפער בין התרחישים: {money(combined['future_deposits'] - baseline['future_deposits'])} נובעים משינוי בהפקדות, ו־{money(combined['growth'] - baseline['growth'])} מהשינוי ברווח המצטבר.")
        funding_rows = [{"תרחיש": FUNDING_LABELS[key], "הפקדות חדשות": money(path[-1]["future_deposits"]),
                         "רווח מהיום": money(path[-1]["growth"]), "שווי עתידי": money(path[-1]["balance"]),
                         "פער מול ההמשך הנוכחי": money(path[-1]["balance"] - baseline["balance"])} for key, path in comparisons.items()]
        st.dataframe(pd.DataFrame(funding_rows), hide_index=True, width="stretch")
    with st.expander("פירוט שנתי והורדה"):
        annual_rows = []
        for row in comparisons["combined"]:
            if row["month"] % 12:
                continue
            item = {"שנים מהיום": row["years"], "סכום התחלתי": initial * factor,
                    "הפקדות חדשות": row["future_deposits"] * factor, "רווח מהיום": row["growth"] * factor, "שווי עתידי": row["balance"] * factor}
            if adjust_inflation:
                item["שווי בכוח הקנייה של היום"] = row["real_value"] * factor
            annual_rows.append(item)
        frame = pd.DataFrame(annual_rows)
        st.dataframe(frame, hide_index=True, width="stretch")
        currency = "ILS" if symbol == "₪" else "USD"
        st.download_button("הורד פירוט שנתי (CSV)", frame.to_csv(index=False).encode("utf-8-sig"),
                           f"investment-projection-{years}y-{focus_rate:g}pct-{currency}.csv", "text/csv", key="projection_download")


@st.fragment
def render_investment_projection(current_value_usd, invested_value_usd, monthly_stats, usd_to_ils, as_of):
    with st.container(key="projection_shell"):
        st.markdown(STYLE, unsafe_allow_html=True)
        st.markdown('<div class="projection-hero"><span class="projection-eyebrow">תכנון השקעות · סימולציה אישית</span>'
                    '<h2>העתיד של התיק שלך</h2><p>מה יקרה אם תמשיך כמו היום — ומה יכול להשתנות עם עוד קצת בכל חודש?</p>'
                    f'<span class="projection-update">נתוני תיק מעודכנים ל־{escape(str(as_of))}</span></div>', unsafe_allow_html=True)
        if not all(math.isfinite(float(v)) for v in (current_value_usd, invested_value_usd, monthly_stats["average"])):
            st.error("לא התקבלו נתוני בסיס תקינים למחשבון. רענן את נתוני התיק.")
            return
        average = max(float(monthly_stats["average"]), 0)
        with st.container(key="projection_source"):
            columns = st.columns(3)
            columns[0].metric("שווי התיק הנוכחי ($)", f"${current_value_usd:,.0f}")
            columns[1].metric("ממוצע הפקדות חודשי שמור ($)", f"${average:,.0f}")
            columns[2].metric("אופק הבדיקה", f"{st.session_state.get('projection_years', 20)} שנים")
        with st.expander("מאיפה מגיעים המספרים?"):
            st.caption(f"שווי ההשקעות ללא מזומן: ${invested_value_usd:,.2f}. ההפקדה הממוצעת היא ${average:,.2f}, לפי ההפקדות הדולריות השמורות לאורך {monthly_stats['months']} חודשים, כולל חודשים ללא הפקדה. רכישות ומכירות מתוך התיק אינן כסף חדש. הסימולציה אינה רושמת פעולות בתיק.")
        with st.container(key="projection_workspace"):
            controls, results = st.columns([1.05, 2.15], gap="large")
            with controls, st.container(border=True, key="projection_controls"):
                years, rate, changed, change_after, lumps, initial, currency, adjust, inflation = _controls(current_value_usd, invested_value_usd, average)
            with results, st.container(border=True, key="projection_results"):
                factor = float(usd_to_ils) if currency == "ILS" else 1.0
                if not math.isfinite(factor) or factor <= 0 or initial < 0:
                    st.error("נתוני השווי או שער ההמרה אינם תקינים; רענן את התיק או בחר תצוגה בדולרים.")
                    return
                symbol = "₪" if currency == "ILS" else "$"
                _results(years, rate, initial, average, changed, change_after, lumps, inflation, adjust, factor, symbol)
                if currency == "ILS":
                    st.caption(f"תצוגה בשער הנוכחי: ₪{usd_to_ils:.4f} לדולר, ללא תחזית לשער המטבע. סכומי ההפקדה מוזנים בדולרים.")
        st.caption("סימולציה בלבד · ללא שינוי בנתוני החשבון · התוצאות תלויות בהנחות שבחרת")
