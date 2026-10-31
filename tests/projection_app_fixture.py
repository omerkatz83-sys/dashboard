"""Offline calculator harness; no account, database or market-data access."""
import streamlit as st

from investment_projection_ui import render_investment_projection

st.set_page_config(page_title="Investment calculator preview", layout="wide")
st.session_state["fixture_parent_runs"] = st.session_state.get("fixture_parent_runs", 0) + 1
holdings, projection = st.tabs(["תיק ההשקעות", "מחשבון"])
with holdings:
    st.write("Account operations would be outside the calculator fragment.")
with projection:
    kwargs = dict(current_value_usd=st.session_state.get("fixture_current", 100000.0),
                  invested_value_usd=80000.0,
                  monthly_stats={"average": 1000.0, "total": 4000.0, "months": 4},
                  usd_to_ils=3.0, as_of="31.10.2026 12:00")
    render_investment_projection(**kwargs)
