import streamlit as st
st.set_page_config(page_title="Portfolio Command Center 2026", layout="wide")
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import os
import json
import math
import uuid
import copy
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client
from market_data import (
    fetch_market_quote,
    normalize_snapshot_quotes,
    quote_has_daily_baseline,
    snapshot_quote_is_fresh,
)

TRADE_COMMISSION_USD = 4.90

# Yahoo Finance uses exchange-qualified symbols for some non-US listings.
# Keep aliases centralized so manually entered purchases resolve consistently.
YAHOO_TICKER_ALIASES = {
    "CNDX": "CNDX.L",  # iShares NASDAQ 100 UCITS ETF USD (LSE)
}


def normalize_market_ticker(ticker):
    normalized = str(ticker or "").strip().upper()
    return YAHOO_TICKER_ALIASES.get(normalized, normalized)


LEGACY_LESSON_STUDENT_ALIASES = {
    "shachar_itay_adva": "itay_adva",
    "itamar": "other",
    "איתמר": "other",
}


def _lesson_number(value, default=0.0):
    """Return a finite float for legacy lesson fields, or None if invalid."""
    if value in (None, ""):
        value = default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_lesson_record(record, source_index):
    """Build a safe analytics view without mutating or dropping the stored record."""
    if not isinstance(record, dict):
        return None, "הרשומה אינה אובייקט נתונים"

    raw_date = str(record.get("date", "")).strip()
    try:
        lesson_date = datetime.strptime(raw_date[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None, "תאריך חסר או לא תקין"

    total = _lesson_number(record.get("total"), default=None)
    duration = _lesson_number(record.get("duration"))
    rate = _lesson_number(record.get("price_per_hour"), default=None)
    if total is None or total < 0:
        return None, "סכום חסר או לא תקין"
    if duration is None or duration < 0:
        return None, "משך שיעור לא תקין"
    if rate is None or rate < 0 or (rate == 0 and duration > 0 and total > 0):
        rate = total / duration if duration > 0 else 0.0

    student = str(record.get("student") or "other").strip()
    student_name = str(record.get("student_name") or "").strip()
    if student in ("itamar", "איתמר") and not student_name:
        student_name = "איתמר"
    student = LEGACY_LESSON_STUDENT_ALIASES.get(student, student)
    payment = record.get("payment", record.get("note", "לא ידוע"))

    return {
        "_source_index": source_index,
        "_archived": bool(record.get("archived_at")),
        "id": str(record.get("id") or ""),
        "student": student,
        "student_name": student_name,
        "date": lesson_date,
        "duration": duration,
        "price_per_hour": rate,
        "total": total,
        "payment": payment,
        "mode": record.get("mode", "legacy"),
        "archived_at": record.get("archived_at"),
    }, None

# --- הגדרת התיק (מחוץ לטאבים - משותף לכולם) ---
portfolio = {
    "VUAA.L": {"qty": 190, "type": "Core", "name": "S&P 500"},
    "IEFA": {"qty": 323, "type": "Core", "name": "Developed Mkts ex-US"},
    "IEMG": {"qty": 258, "type": "Core", "name": "Emerging Markets"},
    "AMZN": {"qty": 9, "type": "Satellite", "name": "Amazon"},
    "COIN": {"qty": 9, "type": "Crypto", "name": "Coinbase"},
    "FBTC": {"qty": 57, "type": "Crypto", "name": "Fidelity Bitcoin"},
    "ETH": {"qty": 98, "type": "Crypto", "name": "Grayscale Ethereum Mini Trust"},
    "PLTR": {"qty": 18,  "type": "Satellite", "name": "Palantir Technologies"},

    "SFL":  {"qty": 200, "type": "Satellite", "name": "SFL Corporation"},
    "BKR":  {"qty": 35,  "type": "Satellite", "name": "Baker Hughes"},
    "IGV":  {"qty": 36,  "type": "Satellite", "name": "iShares Expanded Tech-Software"},
    "NVDA": {"qty": 35,  "type": "Satellite", "name": "Nvidia"},
    "TSLA": {"qty": 7,   "type": "Satellite", "name": "Tesla"},
    "LIN":  {"qty": 7,   "type": "Satellite", "name": "Linde PLC"},
    "PPA":  {"qty": 15,  "type": "Satellite", "name": "Invesco Aerospace & Defense ETF"},
    "CCJ":  {"qty": 27,  "type": "Satellite", "name": "Cameco Corporation"},
    "AVGO": {"qty": 7,   "type": "Satellite", "name": "Broadcom"},
    "APP":  {"qty": 4,   "type": "Satellite", "name": "AppLovin"},
    "IBIT": {"qty": 50,  "type": "Crypto",    "name": "iShares Bitcoin Trust"},
    "KRE":  {"qty": 30,  "type": "Satellite", "name": "SPDR S&P Regional Banking ETF"},
}

# --- מחירי רכישה (Cost Basis) למניה ---
cost_basis = {
    "VUAA.L":       {"price": 130.81, "currency": "USD", "date": "2025-12-01"},
    "IEFA":         {"price": 88.48,  "currency": "USD", "date": "2025-12-01"},
    "IEMG":         {"price": 67.17,  "currency": "USD", "date": "2025-12-01"},
    "AMZN":         {"price": 243.30, "currency": "USD", "date": "2025-12-01"},
    "COIN":         {"price": 385.60, "currency": "USD", "date": "2025-12-01"},
    "FBTC":         {"price": 88.74,  "currency": "USD", "date": "2026-05-11"},
    "ETH":          {"price": 34.92,  "currency": "USD", "date": "2025-12-01"},
    "PLTR":         {"price": 154.50, "currency": "USD", "date": "2026-05-29"},

    "SFL":          {"price": 11.36,  "currency": "USD", "date": "2026-04-30"},
    "BKR":          {"price": 69.24,  "currency": "USD", "date": "2026-05-04"},
    "IGV":          {"price": 91.40,  "currency": "USD", "date": "2026-06-10"},
    "NVDA":         {"price": 216.21, "currency": "USD", "date": "2026-05-26"},
    "TSLA":         {"price": 428.18, "currency": "USD", "date": "2026-05-26"},
    "LIN":          {"price": 509.00, "currency": "USD", "date": "2026-05-13"},
    "PPA":          {"price": 170.01, "currency": "USD", "date": "2026-05-14"},
    "KSM_SP500":    {"price": 2.3603, "currency": "ILS", "date": "2026-05-19"},
    "CCJ":          {"price": 106.78, "currency": "USD", "date": "2026-05-27"},
    "AVGO":         {"price": 379.50, "currency": "USD", "date": "2026-06-12"},
    "APP":          {"price": 563.00, "currency": "USD", "date": "2026-06-04"},
    "IBIT":         {"price": 36.25,  "currency": "USD", "date": "2026-06-08"},
    "KRE":          {"price": 71.00,   "currency": "USD", "date": "2026-06-09"},
}

# --- Data Access Layer ---

class LocalJSONDatabase:
    """Local JSON file-based storage for all app data."""

    def __init__(self):
        _dir = os.path.dirname(os.path.abspath(__file__))
        self._stop_orders_file = os.path.join(_dir, "stop_orders.json")
        self._executed_stops_file = os.path.join(_dir, "executed_stops.json")
        self._sold_stocks_file = os.path.join(_dir, "sold_stocks.json")
        self._lessons_file = os.path.join(_dir, "private_lessons.json")
        self._extra_cash_file = os.path.join(_dir, "extra_cash.json")
        self._il_prices_file = os.path.join(_dir, "il_prices_saved.json")
        self._baseline_file = os.path.join(_dir, "portfolio_baseline.json")
        self._purchased_stocks_file = os.path.join(_dir, "purchased_stocks.json")
        self._dividend_snapshot_file = os.path.join(_dir, "dividend_snapshot.json")
        self._market_snapshot_file = os.path.join(_dir, "market_snapshot.json")

    def _load(self, path, default=None):
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return default if default is not None else {}

    def _save(self, path, data):
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    # --- Stop Orders ---
    def get_stop_orders(self, default=None):
        return self._load(self._stop_orders_file, default)

    def save_stop_orders(self, data):
        return self._save(self._stop_orders_file, data)

    def stop_orders_file_exists(self):
        return os.path.exists(self._stop_orders_file)

    # --- Executed Stops ---
    def get_executed_stops(self):
        return self._load(self._executed_stops_file, [])

    def save_executed_stops(self, data):
        return self._save(self._executed_stops_file, data)

    # --- Sold Stocks ---
    def get_sold_stocks(self):
        return self._load(self._sold_stocks_file, [])

    def save_sold_stocks(self, data):
        return self._save(self._sold_stocks_file, data)

    # --- Lessons ---
    def get_lessons_data(self, default=None):
        if default is None:
            default = {"lessons": [], "students": []}
        return self._load(self._lessons_file, default)

    def save_lessons_data(self, data):
        return self._save(self._lessons_file, data)

    # --- Extra Cash ---
    def get_extra_cash(self):
        return self._load(
            self._extra_cash_file,
            {"total_deposited_usd": 0.0, "total_deposited_ils": 0.0, "deposits": []},
        )

    def save_extra_cash(self, data):
        return self._save(self._extra_cash_file, data)

    # --- IL Prices ---
    def get_il_prices(self):
        return self._load(self._il_prices_file, {})

    def save_il_prices(self, data):
        return self._save(self._il_prices_file, data)

    # --- Baseline ---
    def get_baseline(self):
        return self._load(self._baseline_file, None)

    def save_baseline(self, data):
        return self._save(self._baseline_file, data)

    def baseline_exists(self):
        return os.path.exists(self._baseline_file)

    # --- Purchased Stocks ---
    def get_purchased_stocks(self):
        return self._load(self._purchased_stocks_file, [])

    def save_purchased_stocks(self, data):
        return self._save(self._purchased_stocks_file, data)

    # --- Dividend Snapshot ---
    def get_dividend_snapshot(self):
        return self._load(self._dividend_snapshot_file, {})

    def save_dividend_snapshot(self, data):
        return self._save(self._dividend_snapshot_file, data)

    # --- Market Snapshot ---
    def get_market_snapshot(self):
        return self._load(self._market_snapshot_file, {})

    def save_market_snapshot(self, data):
        return self._save(self._market_snapshot_file, data)

    # --- Received Dividends ---
    def get_received_dividends(self):
        _dir = os.path.dirname(os.path.abspath(__file__))
        return self._load(os.path.join(_dir, "received_dividends.json"), [])

    def save_received_dividends(self, data):
        _dir = os.path.dirname(os.path.abspath(__file__))
        return self._save(os.path.join(_dir, "received_dividends.json"), data)


class SupabaseDatabase:
    """Supabase-based storage — same interface as LocalJSONDatabase."""

    TABLE = "app_state"

    def __init__(self):
        url: str = st.secrets["SUPABASE_URL"]
        key: str = st.secrets["SUPABASE_KEY"]
        self._client: Client = create_client(url, key)

    # --- helpers ---
    def _get(self, row_id, default=None):
        try:
            resp = self._client.table(self.TABLE).select("data").eq("id", row_id).execute()
            if resp.data:
                return resp.data[0]["data"]
        except Exception:
            pass
        return default

    def _set(self, row_id, payload):
        try:
            self._client.table(self.TABLE).upsert({"id": row_id, "data": payload}).execute()
            return True
        except Exception:
            return False

    def _exists(self, row_id):
        try:
            resp = self._client.table(self.TABLE).select("id").eq("id", row_id).execute()
            return bool(resp.data)
        except Exception:
            return False

    # --- Stop Orders ---
    def get_stop_orders(self, default=None):
        return self._get("stop_orders", default)

    def save_stop_orders(self, data):
        return self._set("stop_orders", data)

    def stop_orders_file_exists(self):
        return self._exists("stop_orders")

    # --- Executed Stops ---
    def get_executed_stops(self):
        return self._get("executed_stops", [])

    def save_executed_stops(self, data):
        return self._set("executed_stops", data)

    # --- Sold Stocks ---
    def get_sold_stocks(self):
        return self._get("sold_stocks", [])

    def save_sold_stocks(self, data):
        return self._set("sold_stocks", data)

    # --- Lessons ---
    def get_lessons_data(self, default=None):
        if default is None:
            default = {"lessons": [], "students": []}
        return self._get("lessons", default)

    def save_lessons_data(self, data):
        return self._set("lessons", data)

    # --- Extra Cash ---
    def get_extra_cash(self):
        return self._get(
            "extra_cash",
            {"total_deposited_usd": 0.0, "total_deposited_ils": 0.0, "deposits": []},
        )

    def save_extra_cash(self, data):
        return self._set("extra_cash", data)

    # --- IL Prices ---
    def get_il_prices(self):
        return self._get("il_prices", {})

    def save_il_prices(self, data):
        return self._set("il_prices", data)

    # --- Baseline ---
    def get_baseline(self):
        return self._get("baseline", None)

    def save_baseline(self, data):
        return self._set("baseline", data)

    def baseline_exists(self):
        return self._exists("baseline")

    # --- Purchased Stocks ---
    def get_purchased_stocks(self):
        return self._get("purchased_stocks", [])

    def save_purchased_stocks(self, data):
        return self._set("purchased_stocks", data)

    # --- Dividend Snapshot ---
    def get_dividend_snapshot(self):
        return self._get("dividend_snapshot", {})

    def save_dividend_snapshot(self, data):
        return self._set("dividend_snapshot", data)

    # --- Market Snapshot ---
    def get_market_snapshot(self):
        return self._get("market_snapshot", {})

    def save_market_snapshot(self, data):
        return self._set("market_snapshot", data)

    # --- Received Dividends ---
    def get_received_dividends(self):
        return self._get("received_dividends", [])

    def save_received_dividends(self, data):
        return self._set("received_dividends", data)


db = SupabaseDatabase()

# ברירת מחדל — פקודות סטופ פעילות
default_stop_orders = {
    "IEFA":  {"stop_price": 88.50,  "currency": "USD"},
    "IEMG":  {"stop_price": 77.49,  "currency": "USD"},
    "PLTR":  {"stop_price": 139.40, "currency": "USD"},
    "SFL":   {"stop_price": 11.05,  "currency": "USD"},
    "BKR":   {"stop_price": 66.50,  "currency": "USD"},
    "IGV":   {"stop_price": 87.00,  "currency": "USD"},
    "NVDA":  {"stop_price": 212.00, "currency": "USD"},
    "TSLA":  {"stop_price": 403.00, "currency": "USD"},
    "LIN":   {"stop_price": 495.00, "currency": "USD"},
    "PPA":   {"stop_price": 164.50, "currency": "USD"},
    "CCJ":   {"stop_price": 99.90,  "currency": "USD"},
    "AVGO":  {"stop_price": 361.90, "currency": "USD"},
    "IBIT":  {"stop_price": 33.49,  "currency": "USD"},
    "APP":   {"stop_price": 521.00, "currency": "USD"},
    "KRE":   {"stop_price": 68.50,  "currency": "USD"},
    "XBI":   {"stop_price": 141.00, "currency": "USD"},
}

israeli_stocks = {
    "KSM_SP500": {
        "qty": 9682.00,
        "default_price_ils": 3.3272,
        "yf_ticker": None,
        "fund_id": "5122957",
        "fund_price_divisor": 100,  # המקור מציג מחיר באגורות; התיק מנוהל בשקלים ליחידה
        "type": "Core",
        "name": "S&P 500 (₪)",
        "currency": "ILS"
    },
    "CASH_USD": {
        "qty": 2060,
        "default_price_ils": 1.0,
        "yf_ticker": None,
        "type": "Cash",
        "name": "מזומן ($)",
        "currency": "USD"
    },
}


def _cash_number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _normalize_cash_state(raw_state):
    state = copy.deepcopy(raw_state) if isinstance(raw_state, dict) else {}
    state["total_deposited_usd"] = _cash_number(state.get("total_deposited_usd"))
    state["total_deposited_ils"] = _cash_number(state.get("total_deposited_ils"))
    state["sale_cash_usd"] = _cash_number(state.get("sale_cash_usd"))
    state["sale_cash_ils"] = _cash_number(state.get("sale_cash_ils"))
    state["purchase_deductions_usd"] = _cash_number(state.get("purchase_deductions_usd"))
    if not isinstance(state.get("deposits"), list):
        state["deposits"] = []
    return state


def _average_monthly_usd_deposit(cash_state, today=None):
    """Return average monthly USD deposits since the first saved USD deposit."""
    state = _normalize_cash_state(cash_state)
    deposit_rows = []
    for deposit in state.get("deposits", []):
        if not isinstance(deposit, dict):
            continue
        currency = str(deposit.get("currency", "")).upper()
        amount = _cash_number(deposit.get("amount_usd" if currency == "USD" else "amount"))
        if currency != "USD" or amount <= 0:
            continue
        date_text = str(deposit.get("date", "")).strip()
        try:
            deposit_date = datetime.fromisoformat(date_text.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        deposit_rows.append((deposit_date, amount))

    if not deposit_rows:
        total = state["total_deposited_usd"]
        return {
            "average": round(total, 2) if total > 0 else 0.0,
            "total": round(total, 2),
            "months": 1 if total > 0 else 0,
        }

    total = round(sum(amount for _, amount in deposit_rows), 2)
    first_month = min(deposit_date for deposit_date, _ in deposit_rows)
    end_date = today or datetime.now().date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    month_count = (
        (end_date.year - first_month.year) * 12
        + (end_date.month - first_month.month)
        + 1
    )
    month_count = max(month_count, 1)
    return {
        "average": round(total / month_count, 2),
        "total": total,
        "months": month_count,
    }


def _calculate_purchase_deductions_usd(purchase_records):
    total = 0.0
    for record in purchase_records or []:
        if not _is_valid_purchase_record(record):
            continue
        if str(record.get('currency', 'USD')).upper() != 'USD':
            continue
        commission = max(_cash_number(record.get('commission_usd', TRADE_COMMISSION_USD)), 0.0)
        total += _cash_number(record.get('qty')) * _cash_number(record.get('price')) + commission
    return round(total, 2)


def _prepare_usd_deposit(cash_state, amount_usd, deposit_id=None, deposited_at=None):
    amount = _cash_number(amount_usd)
    if amount <= 0:
        raise ValueError("סכום ההפקדה חייב להיות גדול מאפס")
    state = _normalize_cash_state(cash_state)
    new_deposit_id = deposit_id or uuid.uuid4().hex
    state["total_deposited_usd"] = round(state["total_deposited_usd"] + amount, 2)
    state["deposits"].append({
        "id": new_deposit_id,
        "amount_usd": round(amount, 2),
        "currency": "USD",
        "date": deposited_at or datetime.now().isoformat(timespec='seconds'),
    })
    return state, new_deposit_id


def _cash_balance_usd(base_cash_usd, cash_state, purchase_deductions_usd, usd_to_ils):
    """Return one canonical USD cash balance, preserving legacy ILS cash values."""
    state = _normalize_cash_state(cash_state)
    fx_rate = _cash_number(usd_to_ils)
    if fx_rate <= 0:
        raise ValueError("שער USD/ILS חייב להיות גדול מאפס")
    legacy_ils_cash = state["total_deposited_ils"] + state["sale_cash_ils"]
    balance = (
        _cash_number(base_cash_usd)
        + state["total_deposited_usd"]
        + state["sale_cash_usd"]
        + (legacy_ils_cash / fx_rate)
        - max(_cash_number(purchase_deductions_usd), 0.0)
    )
    return round(balance, 2)


def _is_same_sale(existing_sale, sale_entry):
    try:
        return (
            normalize_market_ticker(existing_sale.get('ticker')) == normalize_market_ticker(sale_entry.get('ticker'))
            and float(existing_sale.get('qty', 0)) == float(sale_entry.get('qty', 0))
            and float(existing_sale.get('sale_price', 0)) == float(sale_entry.get('sale_price', 0))
            and existing_sale.get('date') == sale_entry.get('date')
        )
    except (TypeError, ValueError, AttributeError):
        return False


def _record_timestamp(date_value, registered_at=None):
    """Return a sortable naive timestamp while preserving same-day transaction order when known."""
    date_text = str(date_value or '').strip()
    registered_text = str(registered_at or '').strip()
    candidate = registered_text if registered_text[:10] == date_text[:10] and len(registered_text) > 10 else date_text
    try:
        return datetime.fromisoformat(candidate.replace('Z', '+00:00')).replace(tzinfo=None)
    except (TypeError, ValueError):
        try:
            return datetime.strptime(date_text[:10], '%Y-%m-%d')
        except (TypeError, ValueError):
            return datetime.min


def _purchase_is_after_sale(purchase_record, latest_sale_value):
    if not latest_sale_value:
        return True
    purchase_ts = _record_timestamp(purchase_record.get('date'), purchase_record.get('registered_at'))
    sale_ts = _record_timestamp(latest_sale_value)
    return purchase_ts > sale_ts


def _sale_is_reflected_in_base_position(sale_date, base_purchase_date):
    """Base positions already represent sales made on or before their cost-basis date."""
    if not base_purchase_date:
        return False
    return str(sale_date or '')[:10] <= str(base_purchase_date)[:10]


def _reduce_tracked_position_quantity(ticker, sold_qty):
    """Apply a recorded partial/full sale to the currently tracked base position."""
    ticker = normalize_market_ticker(ticker)
    qty_to_reduce = _cash_number(sold_qty)
    if qty_to_reduce <= 0:
        return 0.0
    remaining_sale_qty = qty_to_reduce
    portfolio_state = globals().get('portfolio', {})
    israeli_state = globals().get('israeli_stocks', {})
    for position_group in (portfolio_state, israeli_state):
        if ticker not in position_group:
            continue
        try:
            current_qty = float(position_group[ticker].get('qty', 0))
        except (TypeError, ValueError, AttributeError):
            current_qty = 0.0
        if current_qty <= 0:
            del position_group[ticker]
            continue
        remaining_position_qty = round(current_qty - remaining_sale_qty, 8)
        if remaining_position_qty > 0:
            position_group[ticker]['qty'] = remaining_position_qty
            remaining_sale_qty = 0.0
            break
        del position_group[ticker]
        remaining_sale_qty = abs(remaining_position_qty)
        if remaining_sale_qty <= 0.000001:
            break
    if ticker not in portfolio_state and ticker not in israeli_state:
        globals().get('cost_basis', {}).pop(ticker, None)
    return round(max(qty_to_reduce - remaining_sale_qty, 0.0), 8)


def _is_valid_purchase_record(record):
    if not isinstance(record, dict) or not record.get('ticker') or record.get('archived_at'):
        return False
    try:
        return float(record.get('qty', 0)) > 0 and float(record.get('price', 0)) > 0
    except (TypeError, ValueError):
        return False


def _effective_purchase_price(price, qty, currency='USD', commission_usd=0.0):
    """Per-share cost including purchase commission for USD trades."""
    price = float(price)
    qty = float(qty)
    commission_usd = float(commission_usd or 0.0)
    if price <= 0 or qty <= 0:
        raise ValueError("מחיר וכמות רכישה חייבים להיות חיוביים")
    if currency == 'USD':
        return (price * qty + commission_usd) / qty
    return price


def _save_state_bundle(steps):
    """Best-effort transaction for the app's separate state rows, with rollback on failure."""
    completed = []
    for save_fn, new_value, old_value in steps:
        if not save_fn(new_value):
            for rollback_fn, rollback_value in reversed(completed):
                rollback_fn(rollback_value)
            return False
        completed.append((save_fn, old_value))
    return True


def _normalize_active_stop_orders(saved_stops, position_tickers):
    """Normalize saved orders without recreating deliberately absent stops."""
    if not isinstance(saved_stops, dict):
        raise ValueError("נתוני הסטופים אינם תקינים; לא בוצע שינוי")
    positions = {normalize_market_ticker(ticker) for ticker in position_tickers}
    normalized = {}
    for ticker, order in saved_stops.items():
        key = normalize_market_ticker(ticker)
        if key not in positions:
            continue
        if isinstance(order, (int, float)):
            order = {"stop_price": float(order), "currency": "USD"}
        if not isinstance(order, dict):
            continue
        try:
            price = float(order.get("stop_price", 0))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(price) or price <= 0:
            continue
        normalized[key] = copy.deepcopy(order)
    return normalized, normalized != saved_stops


def _record_sale(
    db_obj, ticker, name, qty, sale_price, currency, sale_date,
    stop_price=None, reason='manual', fx_rate=None,
):
    ticker = normalize_market_ticker(ticker)
    qty = float(qty)
    sale_price = float(sale_price)
    currency = str(currency or 'USD').upper()
    if qty <= 0 or sale_price <= 0:
        raise ValueError("כמות ומחיר מכירה חייבים להיות גדולים מאפס")
    if currency not in {'USD', 'ILS'}:
        raise ValueError("מטבע המכירה חייב להיות USD או ILS")
    _cb_info = cost_basis.get(ticker, {})
    _cost_per = _cb_info.get('price')
    _commission = TRADE_COMMISSION_USD
    _fx_rate = float(fx_rate or 0.0)
    if _fx_rate < 0:
        raise ValueError("שער ההמרה לא יכול להיות שלילי")
    _commission_ils = round(_commission * _fx_rate, 2) if currency == 'ILS' and _fx_rate else None
    if currency == 'USD':
        _proceeds = round((sale_price * qty) - _commission, 2)
    else:
        _proceeds = round(sale_price * qty, 2)

    sale_entry = {
        'id': uuid.uuid4().hex,
        'ticker': ticker,
        'name': name,
        'qty': qty,
        'stop_price': stop_price,
        'sale_price': sale_price,
        'proceeds': _proceeds,
        'cost_per_share': _cost_per,
        'commission_usd': _commission,
        'commission_ils': _commission_ils,
        'fx_rate_at_sale': _fx_rate or None,
        'currency': currency,
        'reason': reason,
        'date': sale_date,
        'recorded_at': datetime.now().isoformat(timespec='seconds'),
    }

    _old_sold_stocks = db_obj.get_sold_stocks() or []
    _old_executed_history = db_obj.get_executed_stops() or []
    _old_active_stops = db_obj.get_stop_orders(default_stop_orders.copy()) or {}
    _old_cash_state = _normalize_cash_state(db_obj.get_extra_cash())
    if not isinstance(_old_sold_stocks, list) or not isinstance(_old_executed_history, list):
        raise RuntimeError("נתוני היסטוריית המכירות אינם תקינים; לא בוצע שינוי")
    if not isinstance(_old_active_stops, dict):
        raise RuntimeError("נתוני פקודות הסטופ אינם תקינים; לא בוצע שינוי")
    sold_stocks_data = copy.deepcopy(_old_sold_stocks)
    executed_history = copy.deepcopy(_old_executed_history)
    active_stops = copy.deepcopy(_old_active_stops)
    cash_state = copy.deepcopy(_old_cash_state)

    if any(_is_same_sale(item, sale_entry) for item in sold_stocks_data):
        raise ValueError("המכירה כבר נרשמה; המזומן לא עודכן שוב")
    sold_stocks_data.append(sale_entry)
    if not any(_is_same_sale(item, sale_entry) for item in executed_history):
        executed_history.append(copy.deepcopy(sale_entry))

    if currency == 'ILS':
        cash_state['sale_cash_ils'] += _proceeds
        cash_state['sale_cash_usd'] -= _commission
    else:
        cash_state['sale_cash_usd'] += _proceeds

    _current_position_qty = 0.0
    for _position_group in (globals().get('portfolio', {}), globals().get('israeli_stocks', {})):
        if ticker in _position_group:
            try:
                _current_position_qty += float(_position_group[ticker].get('qty', 0))
            except (TypeError, ValueError, AttributeError):
                pass
    if ticker in active_stops and _current_position_qty - qty <= 0.000001:
        del active_stops[ticker]

    if not _save_state_bundle([
        (db_obj.save_sold_stocks, sold_stocks_data, _old_sold_stocks),
        (db_obj.save_executed_stops, executed_history, _old_executed_history),
        (db_obj.save_stop_orders, active_stops, _old_active_stops),
        (db_obj.save_extra_cash, cash_state, _old_cash_state),
    ]):
        raise RuntimeError("שמירת המכירה נכשלה; בוצע ניסיון שחזור של המצב הקודם")
    return sale_entry

# --- טעינת מכירות (סטופים שבוצעו) — הסרת מניות שנמכרו + הוספת תמורה למזומן ---
_sold_stocks = db.get_sold_stocks() or []
if not isinstance(_sold_stocks, list):
    _sold_stocks = []
# קבץ לפי טיקר — שמור רק את תאריך המכירה האחרון לכל טיקר
_latest_sale_date = {}
_sold_qty_after_base = {}
for _sold in _sold_stocks:
    if not isinstance(_sold, dict) or not _sold.get('ticker'):
        continue
    _t = normalize_market_ticker(_sold['ticker'])
    _sd = _sold.get('date', '')
    if _t not in _latest_sale_date or _sd > _latest_sale_date[_t]:
        _latest_sale_date[_t] = _sd
    _purchase_date_cb = cost_basis.get(_t, {}).get('date', '')
    if _sale_is_reflected_in_base_position(_sd, _purchase_date_cb):
        continue
    try:
        _sq = float(_sold.get('qty', 0))
    except (TypeError, ValueError):
        _sq = 0.0
    if _sq > 0:
        _sold_qty_after_base[_t] = _sold_qty_after_base.get(_t, 0.0) + _sq
for _t, _sold_qty in _sold_qty_after_base.items():
    _reduce_tracked_position_quantity(_t, _sold_qty)

# --- טעינת רכישות ידניות שנשמרו דרך הדשבורד ---
_all_purchased_stocks = db.get_purchased_stocks() or []
if not isinstance(_all_purchased_stocks, list):
    _all_purchased_stocks = []
_purchased_stocks = [
    _ps for _ps in _all_purchased_stocks
    if _is_valid_purchase_record(_ps)
]
_reopened_tickers = set()
for _ps in sorted(
    _purchased_stocks,
    key=lambda item: _record_timestamp(item.get('date'), item.get('registered_at')),
):
    if not _ps.get('ticker'):
        continue
    _pt = normalize_market_ticker(_ps['ticker'])
    # בדוק אם נמכרה אחרי — אם כן, אל תוסיף
    _last_sale = _latest_sale_date.get(_pt, '')
    _buy_date = _ps.get('date', '')
    if _last_sale and not _purchase_is_after_sale(_ps, _last_sale):
        continue  # נמכרה אחרי הרכישה — לא להוסיף
    _first_purchase_after_sale = bool(_last_sale) and _pt not in _reopened_tickers
    if _first_purchase_after_sale:
        # פוזיציה שנפתחה מחדש לא יורשת סטופ ישן מהפוזיציה שנמכרה.
        default_stop_orders.pop(_pt, None)
        _reopened_tickers.add(_pt)
    try:
        _add_qty = float(_ps['qty'])
        _add_price = float(_ps['price'])
    except (TypeError, ValueError, KeyError):
        continue
    if _add_qty <= 0 or _add_price <= 0:
        continue
    _add_currency = _ps.get('currency', 'USD')
    _purchase_commission = float(
        _ps.get('commission_usd', TRADE_COMMISSION_USD if _add_currency == 'USD' else 0.0)
    )
    _effective_add_price = _effective_purchase_price(
        _add_price, _add_qty, _add_currency, _purchase_commission
    )

    if _pt in portfolio:
        # טיקר קיים — הוסף כמות וחשב ממוצע משוקלל
        _existing_qty = float(portfolio[_pt]['qty'])
        _existing_price = float(cost_basis.get(_pt, {}).get('price', _add_price))
        _original_date = cost_basis.get(_pt, {}).get('date', _buy_date[:10])
        _total_qty = _existing_qty + _add_qty
        portfolio[_pt]['qty'] = _total_qty
        if _total_qty > 0:
            cost_basis[_pt] = {
                'price': round((_existing_price * _existing_qty + _effective_add_price * _add_qty) / _total_qty, 4),
                'currency': cost_basis.get(_pt, {}).get('currency', _add_currency),
                'date': _original_date,  # שמור תאריך רכישה מקורי — לא תאריך התוספת
                'last_add_date': _buy_date[:10],
                'last_add_qty': _add_qty,
                'last_add_price': _effective_add_price,
            }
    else:
        # טיקר חדש — צור ערך חדש
        portfolio[_pt] = {
            'qty': _add_qty,
            'type': _ps.get('type', 'Satellite'),
            'name': _ps.get('name', _pt),
        }
        cost_basis[_pt] = {
            'price': _effective_add_price,
            'currency': _add_currency,
            'date': _buy_date[:10],
        }
    # הסטופ האחרון שהוגדר ברכישה הוא ברירת המחדל לשחזור מצב.
    if _ps.get('stop_price'):
        default_stop_orders[_pt] = {
            'stop_price': float(_ps['stop_price']),
            'currency': _ps.get('stop_currency', _add_currency),
        }

# --- פונקציות (מחוץ לטאבים - משותף לכולם) ---

def calc_atr(hist_df, period=14):
    """חישוב ATR (Average True Range) מ-DataFrame של yfinance"""
    if hist_df is None or len(hist_df) < period + 1:
        return None
    h = hist_df['High'].values
    l = hist_df['Low'].values
    c = hist_df['Close'].values
    tr = []
    for i in range(1, len(h)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1])))
    if len(tr) < period:
        return sum(tr) / len(tr) if tr else None
    return sum(tr[-period:]) / period

def parse_mutual_fund_purchase_price(page_html):
    """Extract the purchase quote (agorot) from the Bizportal fund header."""
    import re as _re
    if not page_html:
        return None
    marker_index = page_html.find('id="paper_change"')
    if marker_index < 0:
        return None
    header_block = page_html[marker_index:marker_index + 2500]
    quoted_numbers = _re.findall(
        r'<div\s+class="num">\s*([\d,.]+)\s*</div>',
        header_block,
        flags=_re.IGNORECASE,
    )
    if not quoted_numbers:
        return None
    # הכותרת מציגה מחיר פדיון ולאחריו מחיר קנייה. אם קיים רק ערך אחד, השתמש בו.
    raw_value = quoted_numbers[1] if len(quoted_numbers) > 1 else quoted_numbers[0]
    try:
        price = float(raw_value.replace(',', ''))
    except (TypeError, ValueError):
        return None
    return price if 10 <= price <= 100000 else None


def get_mutual_fund_price(fund_id):
    """Fetch a fresh Israeli mutual-fund purchase quote in agorot."""
    try:
        response = requests.get(
            f'https://www.bizportal.co.il/mutualfunds/quote/generalview/{fund_id}',
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'he-IL,he;q=0.9,en;q=0.8',
            },
            timeout=15
        )
        if response.ok:
            return parse_mutual_fund_purchase_price(response.text)
    except requests.RequestException:
        return None
    return None

def _fund_target_refresh_date():
    """תאריך יעד לעדכון מחיר קרן: אחרי 12:00 ישראל היום, ולפני כן יום קודם."""
    from datetime import timedelta
    import pytz
    now_il = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Jerusalem'))
    if now_il.hour >= 12:
        return now_il.strftime('%Y-%m-%d')
    return (now_il - timedelta(days=1)).strftime('%Y-%m-%d')

@st.cache_data(ttl=300)
def get_israeli_price(yf_ticker):
    """ניסיון משיכת מחיר נייר ערך ישראלי מ-Yahoo Finance (.TA)"""
    if not yf_ticker:
        return None
    try:
        t = yf.Ticker(yf_ticker)
        hist = t.history(period="5d")
        if not hist.empty:
            price_agorot = float(hist['Close'].iloc[-1])
            # Yahoo Finance מחזיר מחירי ת"א באגורות (ILA) - צריך לחלק ב-100
            currency = t.info.get('currency', 'ILA')
            if currency == 'ILA':
                return price_agorot / 100  # המרה משקלים לשקלים
            return price_agorot
    except:
        pass
    return None

@st.cache_data(ttl=30)
def get_usd_to_ils():
    """משיכת שער דולר-שקל עדכני"""
    try:
        ils_usd = yf.Ticker("ILS=X")
        hist = ils_usd.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        else:
            usd_ils = yf.Ticker("USDILS=X")
            hist = usd_ils.history(period="1d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
    except:
        pass
    return 3.65

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_live_dividends(tickers_list):
    """משיכת נתוני דיבידנד עדכניים מ-yfinance (רק בלחיצה על כפתור)"""
    from datetime import datetime, timedelta
    result = {}
    for ticker in tickers_list:
        try:
            t = yf.Ticker(ticker)
            divs = t.dividends
            annual = 0.0
            if divs is not None and len(divs) > 0:
                cutoff = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
                recent = divs.loc[cutoff:]
                if len(recent) > 0:
                    annual = float(recent.sum())
            if annual <= 0:
                info = t.info
                rate = info.get('trailingAnnualDividendRate') or info.get('dividendRate')
                if rate and rate > 0:
                    annual = float(rate)
                else:
                    yld = info.get('yield') or info.get('trailingAnnualDividendYield')
                    price = info.get('regularMarketPrice', 0)
                    if yld and yld > 0 and price:
                        annual = price * float(yld)
            if annual > 0:
                result[ticker] = round(annual, 4)
        except:
            pass
    return result

@st.cache_data(ttl=300, show_spinner=False)
def fetch_notification_data(tickers_tuple):
    """משיכת נתוני 52-week high + תאריך אקס-דיבידנד + תאריך תשלום לכל הטיקרים"""
    data = {}
    for ticker in tickers_tuple:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            data[ticker] = {
                '52w_high': info.get('fiftyTwoWeekHigh'),
                '52w_low': info.get('fiftyTwoWeekLow'),
                'ex_div_date': info.get('exDividendDate'),   # unix timestamp
                'div_date': info.get('dividendDate'),        # unix timestamp — תאריך תשלום בפועל
                'div_rate': info.get('trailingAnnualDividendRate'),
                'name': info.get('shortName', ticker),
            }
        except:
            data[ticker] = {}
    return data

@st.cache_data(ttl=30)
def get_data(portfolio):
    portfolio_df = []
    history_dict = {}
    errors = []
    snapshot_quotes = normalize_snapshot_quotes(db.get_market_snapshot())
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_tickers = len(portfolio)
    
    for idx, (ticker, info) in enumerate(portfolio.items()):
        status_text.text(f'טוען {ticker} ({idx+1}/{total_tickers})...')
        progress_bar.progress((idx + 1) / total_tickers)
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            
            if hist.empty:
                errors.append(f"{ticker}: אין נתונים היסטוריים")
                continue
            
            # הסרת שורות עם NaN ב-Close (למשל כשהשוק עדיין פתוח)
            hist_clean = hist.dropna(subset=['Close'])
            if hist_clean.empty:
                errors.append(f"{ticker}: אין נתוני מחיר תקפים")
                continue
            
            history_dict[ticker] = hist

            quote, intraday_clean = fetch_market_quote(ticker, stock=stock, history=hist_clean)
            if intraday_clean is not None:
                # שמור את ה-DataFrame המלא לסינון לפי חותמת זמן בבדיקות סטופ
                history_dict[f"{ticker}__intraday"] = intraday_clean

            snapshot_quote = snapshot_quotes.get(ticker, {})
            if snapshot_quote_is_fresh(snapshot_quote):
                quote = {**snapshot_quote, "source": "supabase_market_snapshot"}
            elif not quote_has_daily_baseline(quote) and quote_has_daily_baseline(snapshot_quote):
                quote = {**snapshot_quote, "source": "supabase_market_snapshot"}

            price = quote.get('price')
            if price is None:
                price = float(hist_clean['Close'].iloc[-1])
            else:
                price = float(price)

            prev_close = quote.get('previous_close')
            if prev_close is None:
                prev_close = float(hist_clean['Close'].iloc[-1]) if len(hist_clean) > 0 else price
                if len(hist_clean) > 1:
                    prev_close = float(hist_clean['Close'].iloc[-2])
            else:
                prev_close = float(prev_close)
            
            # אם מניה נקנתה/הוגדלה היום — תקן את Prev Close בהתאם
            cb = cost_basis.get(ticker)
            if cb and cb.get('date'):
                from datetime import date as _date
                try:
                    _today_str = _date.today().isoformat()
                    buy_date = _date.fromisoformat(cb['date'])
                    # תוספת לפוזיציה קיימת (last_add_date) — מנגנון חדש
                    if cb.get('last_add_date') == _today_str:
                        _add_qty = cb.get('last_add_qty', 0)
                        _add_price = cb.get('last_add_price', 0)
                        _old_qty = info['qty'] - _add_qty
                        if _old_qty == 0 and _add_qty > 0:
                            # פוזיציה חדשה לגמרי שנקנתה היום — השינוי היומי מחושב ממחיר הקנייה
                            prev_close = _add_price if _add_price > 0 else cb['price']
                        # תוספת לפוזיציה קיימת (_old_qty > 0): prev_close נשאר מחיר השוק של אתמול
                    # פוזיציה שנקנתה כולה היום — מנגנון ישן + תאימות לאחור
                    elif buy_date == _date.today():
                        today_buy_qty = cb.get('today_buy_qty')
                        if today_buy_qty and today_buy_qty < info['qty']:
                            # תמיכה בשדה ישן today_buy_qty
                            old_qty = info['qty'] - today_buy_qty
                            today_buy_price = cb.get('today_buy_price', cb['price'])
                            prev_close = (prev_close * old_qty + today_buy_price * today_buy_qty) / info['qty']
                        else:
                            # פוזיציה חדשה לגמרי שנקנתה היום
                            prev_close = cb['price']
                except ValueError:
                    pass
            
            value = price * info['qty']
            
            portfolio_df.append({
                "Ticker": ticker,
                "Name": info['name'],
                "Type": info['type'],
                "Quantity": info['qty'],
                "Price": price,
                "Prev Close": prev_close,
                "Value": value
            })
            
        except Exception as e:
            errors.append(f"{ticker}: {str(e)}")
    
    progress_bar.empty()
    status_text.empty()
    
    if errors:
        with st.expander("⚠️ שגיאות בטעינת נתונים", expanded=False):
            for error in errors:
                st.warning(error)
    
    return pd.DataFrame(portfolio_df), history_dict

@st.cache_data(ttl=60)  # cache רק ל-60 שניות לנתונים עדכניים
def get_stock_insights(ticker, info):
    """מחלץ תובנות מהמניה"""
    insights = {}
    
    try:
        insights['name'] = info.get('longName', info.get('shortName', ticker))
        insights['sector'] = info.get('sector', 'N/A')
        insights['industry'] = info.get('industry', 'N/A')
        insights['current_price'] = info.get('currentPrice', info.get('regularMarketPrice', 0))
        insights['target_mean'] = info.get('targetMeanPrice', None)
        insights['target_high'] = info.get('targetHighPrice', None)
        insights['target_low'] = info.get('targetLowPrice', None)
        insights['recommendation'] = info.get('recommendationKey', 'N/A')
        insights['num_analysts'] = info.get('numberOfAnalystOpinions', 0)
        insights['market_cap'] = info.get('marketCap', 0)
        insights['pe_ratio'] = info.get('trailingPE', None)
        insights['forward_pe'] = info.get('forwardPE', None)
        insights['peg_ratio'] = info.get('pegRatio', None)
        insights['dividend_yield'] = info.get('dividendYield', None)
        insights['52w_high'] = info.get('fiftyTwoWeekHigh', None)
        insights['52w_low'] = info.get('fiftyTwoWeekLow', None)
        insights['50d_avg'] = info.get('fiftyDayAverage', None)
        insights['200d_avg'] = info.get('twoHundredDayAverage', None)
        insights['ytd_return'] = info.get('ytdReturn', None)
    except Exception as e:
        st.error(f"שגיאה בטעינת נתונים עבור {ticker}: {str(e)}")
    
    return insights

# --- טאבים לניווט ---
main_tab, lessons_tab = st.tabs(["📊 דשבורד ראשי", "📚 שיעורים פרטיים"])

# ==================== TAB 1: דשבורד ראשי ====================
with main_tab:
    st.title("📊 דשבורד ניהול השקעות - Core/Satellite")

    # מחשבון איזון מחדש (Rebalancing Calculator)
    st.sidebar.markdown("---")
    st.sidebar.header("⚖️ מחשבון איזון מחדש")
    st.sidebar.caption("הכנס סכום הפקדה חדשה וקבל פיזור אופטימלי לפי האסטרטגיה שלך, **בלי למכור נכסים קיימים** (משיקולי מס).")
    
    target_alloc = {"Core": 0.79, "Satellite": 0.15, "Crypto": 0.06}
    target_labels = {"Core": "🏛️ ליבה (Core)", "Satellite": "🛰️ לוויין (Satellite)", "Crypto": "₿ קריפטו (Crypto)"}
    
    new_deposit = st.sidebar.number_input(
        "💰 כמה אתה רוצה להפקיד? (₪)",
        min_value=0.0, value=0.0, step=500.0, format="%.0f"
    )

    # --- עדכון מחירי נכסים ישראליים ---
    st.sidebar.markdown("---")
    st.sidebar.header("🇮🇱 נכסים ישראליים ומזומן")
    
    # טעינת הפקדות מזומן מצטברות מקובץ
    _saved_deposits = _normalize_cash_state(db.get_extra_cash())
    _total_deposited_usd = _saved_deposits["total_deposited_usd"]
    _total_deposited_ils = _saved_deposits["total_deposited_ils"]
    # חישוב דינמי — סך כל עלויות הרכישות שנרשמו + עמלות
    _purchase_deductions_usd = _calculate_purchase_deductions_usd(_purchased_stocks)
    
    _new_cash_deposit_usd = st.sidebar.number_input(
        "💵 הפקדת מזומן חדשה ($)",
        min_value=0.0, value=0.0, step=100.0, format="%.2f",
        help="הקלד את סכום ההפקדה בדולרים. הסכום יישמר ויתווסף ישירות ליתרת המזומן הדולרית.",
    )
    
    if st.sidebar.button("✅ הפקד דולרים", disabled=(_new_cash_deposit_usd <= 0)):
        _deposit_state, _deposit_id = _prepare_usd_deposit(
            _saved_deposits, _new_cash_deposit_usd
        )
        _expected_deposited_usd = _deposit_state["total_deposited_usd"]
        if db.save_extra_cash(_deposit_state):
            _verified_cash_state = _normalize_cash_state(db.get_extra_cash())
            _deposit_verified = (
                abs(_verified_cash_state["total_deposited_usd"] - _expected_deposited_usd) < 0.005
                and any(
                    isinstance(item, dict) and item.get("id") == _deposit_id
                    for item in _verified_cash_state["deposits"]
                )
            )
            if _deposit_verified:
                _saved_deposits = _verified_cash_state
                _total_deposited_usd = _expected_deposited_usd
                st.sidebar.success(f"✅ הופקדו ${_new_cash_deposit_usd:,.2f} ונשמרו בהצלחה.")
            else:
                st.sidebar.error("ההפקדה נשלחה אך לא אומתה. יש לרענן לפני ניסיון נוסף כדי למנוע הפקדה כפולה.")
        else:
            st.sidebar.error("ההפקדה לא נשמרה; יתרת המזומן לא שונתה.")
    
    if _total_deposited_usd > 0:
        st.sidebar.caption(f"💰 סה״כ הפקדות דולריות: ${_total_deposited_usd:,.2f}")
        _avg_deposit_stats = _average_monthly_usd_deposit(_saved_deposits)
        st.sidebar.metric(
            "📆 ממוצע הפקדות מזומן בחודש",
            f"${_avg_deposit_stats['average']:,.2f}",
            help=(
                "מחושב מסך ההפקדות הדולריות השמורות, "
                f"מהחודש הראשון עם הפקדה ועד היום ({_avg_deposit_stats['months']} חודשים)."
            ),
        )
    if _total_deposited_ils > 0:
        st.sidebar.caption(f"🗂️ הפקדות עבר בשקלים שנשמרו: ₪{_total_deposited_ils:,.2f}")
    
    st.sidebar.caption("מחירי קרנות ישראליות:")
    
    # --- שמירת מחירים לקובץ JSON כדי ששום rerun לא ימחק אותם ---
    saved_prices = db.get_il_prices() or {}
    if not isinstance(saved_prices, dict):
        saved_prices = {}
        st.sidebar.error("נתוני המחירים השמורים אינם תקינים; לא בוצעה דריסה שלהם.")
    
    il_prices = {}
    _il_prices_changed = False
    for ticker, info in israeli_stocks.items():
        if info.get('currency') == 'USD' or ticker == 'CASH_USD':
            il_prices[ticker] = info['default_price_ils']
            continue
        
        # --- קרנות נאמנות ישראליות — מחיר אוטומטי ושמירה מאומתת ---
        _fund_id = info.get('fund_id') or info.get('funder_id')
        if _fund_id:
            _marker_key = f"__fund_last_update__{ticker}"
            _timestamp_key = f"__fund_last_update_ts__{ticker}"
            _source_key = f"__fund_price_source__{ticker}"
            _raw_key = f"__fund_raw_price__{ticker}"
            _target_date = _fund_target_refresh_date()
            _needs_refresh = saved_prices.get(_marker_key) != _target_date

            # הכפתור תמיד מבצע קריאה חדשה; אין cache שמחזיר ערך ישן.
            _col1, _col2 = st.sidebar.columns([3, 1])
            _force_refresh = _col2.button(
                "🔄",
                key=f"force_refresh_{ticker}",
                help=f"משוך ושמור מחיר קנייה עדכני עבור {info['name']}",
            )
            _refresh_requested = _needs_refresh or _force_refresh

            # רענון פעם ביום לפי תאריך היעד
            if _refresh_requested:
                _fund_raw = get_mutual_fund_price(_fund_id)
                _divisor = float(info.get('fund_price_divisor', info.get('funder_divisor', 1)))
                _fund_price_ils = round(_fund_raw / _divisor, 6) if _fund_raw and _divisor > 0 else None
                if _fund_price_ils and 0.01 <= _fund_price_ils <= 10000:
                    _candidate_prices = dict(saved_prices)
                    _candidate_prices[ticker] = _fund_price_ils
                    _candidate_prices[_marker_key] = _target_date
                    _candidate_prices[_timestamp_key] = datetime.now().isoformat(timespec="seconds")
                    _candidate_prices[_source_key] = "bizportal_purchase_price"
                    _candidate_prices[_raw_key] = _fund_raw
                    if db.save_il_prices(_candidate_prices):
                        _verified_prices = db.get_il_prices() or {}
                        _verified_price = _lesson_number(_verified_prices.get(ticker), default=None)
                        if _verified_price is not None and abs(_verified_price - _fund_price_ils) < 0.000001:
                            saved_prices = _verified_prices
                            if _force_refresh:
                                st.sidebar.success(f"נשמר מחיר חדש: ₪{_fund_price_ils:.4f}")
                        else:
                            st.sidebar.error("המחיר נשלח לשמירה אך לא אומת בקריאה חוזרת.")
                    else:
                        st.sidebar.error("משיכת המחיר הצליחה, אך השמירה נכשלה.")
                elif _force_refresh:
                    st.sidebar.error("לא התקבל מחיר קנייה תקין מהמקור. המחיר השמור לא שונה.")

            if ticker in saved_prices:
                il_prices[ticker] = float(saved_prices[ticker])
                _updated_at = saved_prices.get(_timestamp_key, saved_prices.get(_marker_key, "לא ידוע"))
                _col1.caption(f"💰 {info['name']} ✅ ₪{il_prices[ticker]:.4f}")
                _col1.caption(f"עודכן: {_updated_at}")
            else:
                il_prices[ticker] = info['default_price_ils']
                _col1.caption(f"💰 {info['name']} ⚠️ ₪{il_prices[ticker]:.4f} (ברירת מחדל)")
            continue
        
        sk = f"il_price_{ticker}"
        
        # סדר עדיפויות: 1) Yahoo Finance 2) מחיר שנשמר 3) ברירת מחדל
        auto_price = get_israeli_price(info.get('yf_ticker'))

        if auto_price:
            initial_val = auto_price
            source_label = " ✅"
        elif ticker in saved_prices:
            initial_val = saved_prices[ticker]
            source_label = " ✏️"
        else:
            initial_val = info['default_price_ils']
            source_label = " (ידני)"
        
        il_prices[ticker] = st.sidebar.number_input(
            f"💰 {info['name']}{source_label}",
            min_value=0.01,
            value=float(initial_val),
            step=0.01,
            format="%.2f",
            key=sk,
            help=f"כמות: {info['qty']:.2f} | ברירת מחדל: ₪{info['default_price_ils']:.2f}"
        )
        
        # שמור רק אם המשתמש שינה את הערך בפועל
        if abs(il_prices[ticker] - initial_val) > 0.001:
            saved_prices[ticker] = il_prices[ticker]
            _il_prices_changed = True
        elif ticker not in saved_prices:
            # טיקר חדש שלא היה ב-DB — שמור את הערך הראשוני
            saved_prices[ticker] = il_prices[ticker]
            _il_prices_changed = True
    
    # שמור רק אם משהו השתנה
    if _il_prices_changed:
        if not db.save_il_prices(saved_prices):
            st.sidebar.error("שמירת המחירים הידניים נכשלה; הערכים הקודמים נשמרו.")

    # כפתור רענון
    col_refresh, col_empty = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 רענן נתונים"):
            st.cache_data.clear()
            st.rerun()

    try:
        df, history_data = get_data(portfolio)
        if df.empty:
            st.error("❌ לא נטענו נתונים כלל! בדוק חיבור לאינטרנט או תקינות הטיקרים.")
            st.stop()
        usd_to_ils = get_usd_to_ils()
        df['Value ILS'] = df['Value'] * usd_to_ils
        # הוספת מניות ישראליות ומזומן
        israeli_rows = []
        for ticker, info in israeli_stocks.items():
            price_ils = il_prices.get(ticker, info['default_price_ils'])
            qty = info['qty']
            
            # יתרת המזומן מחושבת במקום אחד כדי שהפקדות, מכירות ורכישות יישארו עקביות.
            if ticker == 'CASH_USD':
                qty = _cash_balance_usd(
                    base_cash_usd=qty,
                    cash_state=_saved_deposits,
                    purchase_deductions_usd=_purchase_deductions_usd,
                    usd_to_ils=usd_to_ils,
                )
            
            if info.get('currency') == 'USD':
                price_usd = price_ils
                value_usd = qty
                value_ils = value_usd * usd_to_ils
            else:
                price_usd = price_ils / usd_to_ils
                value_usd = price_usd * qty
                value_ils = price_ils * qty
            israeli_rows.append({
                "Ticker": ticker,
                "Name": info['name'],
                "Type": info['type'],
                "Quantity": qty,
                "Price": price_usd,
                "Prev Close": price_usd,
                "Value": value_usd,
                "Value ILS": value_ils
            })
        if israeli_rows:
            israeli_df = pd.DataFrame(israeli_rows)
            df = pd.concat([df, israeli_df], ignore_index=True)

        _cash_row = df[df['Ticker'] == 'CASH_USD']
        if not _cash_row.empty:
            _current_cash_usd = float(_cash_row.iloc[0]['Quantity'])
            st.sidebar.caption(f"💵 יתרת מזומן נוכחית: ${_current_cash_usd:,.2f}")
            if _current_cash_usd < -0.01:
                st.sidebar.warning("יתרת המזומן שלילית. בדוק שהרכישות וההפקדות שנרשמו תואמות לחשבון.")
        
        total_value = df['Value'].sum()
        total_value_ils = df['Value ILS'].sum()
        
        # שווי תיק ללא מזומן — לחישוב רווח/הפסד (כדי שהוספת מזומן לא תיראה כרווח)
        _invested_mask = df['Type'] != 'Cash'
        total_invested = df.loc[_invested_mask, 'Value'].sum()
        total_invested_ils = df.loc[_invested_mask, 'Value ILS'].sum()

        # מחשבון איזון מחדש
        if new_deposit > 0:
            new_total = total_value_ils + new_deposit
            
            st.sidebar.markdown("---")
            st.sidebar.subheader("📊 תוצאות המחשבון")
            st.sidebar.markdown(f"**שווי תיק נוכחי:** ₪{total_value_ils:,.0f}")
            st.sidebar.markdown(f"**הפקדה חדשה:** ₪{new_deposit:,.0f}")
            st.sidebar.markdown(f"**שווי לאחר הפקדה:** ₪{new_total:,.0f}")
            st.sidebar.markdown("---")
            
            total_to_distribute = 0
            alloc_details = []
            
            for k in target_alloc:
                current_val = df[df['Type'] == k]['Value ILS'].sum()
                current_pct = (current_val / total_value_ils * 100) if total_value_ils > 0 else 0
                target_pct = target_alloc[k] * 100
                target_val = target_alloc[k] * new_total
                gap = max(target_val - current_val, 0)
                total_to_distribute += gap
                alloc_details.append({
                    'key': k,
                    'current_val': current_val,
                    'current_pct': current_pct,
                    'target_pct': target_pct,
                    'gap': gap
                })
            
            # נרמול: אם סכום הפערים גדול מההפקדה, נחלק פרופורציונלית
            if total_to_distribute > 0:
                scale = min(new_deposit / total_to_distribute, 1.0)
            else:
                scale = 0
            
            st.sidebar.markdown("**כך כדאי לפזר את ההפקדה:**")
            for item in alloc_details:
                k = item['key']
                label = target_labels.get(k, k)
                amount = item['gap'] * scale
                pct_of_deposit = (amount / new_deposit * 100) if new_deposit > 0 else 0
                
                st.sidebar.markdown(
                    f"{label}\n"
                    f"- 👉 **הפקד: ₪{amount:,.0f}** ({pct_of_deposit:.0f}% מההפקדה)\n"
                    f"- מצב נוכחי: {item['current_pct']:.1f}% → יעד: {item['target_pct']:.0f}%"
                )
            
            remaining = new_deposit - sum(item['gap'] * scale for item in alloc_details)
            if remaining > 10:
                st.sidebar.success(f"✅ עודף של ₪{remaining:,.0f} - התיק כבר מאוזן היטב! הפקד לפי שיקול דעתך.")
            
            st.sidebar.markdown("---")
            st.sidebar.caption("💡 החישוב מתבסס על האסטרטגיה: 79% ליבה, 15% לוויין, 6% קריפטו. ההפקדה מתוכננת לקרב אותך ליעדים **בלי למכור** נכסים קיימים.")
        df['Portfolio %'] = (df['Value'] / total_value * 100).round(2)
        
        total_assets = len(portfolio) + len(israeli_stocks)
        st.success(f"✅ נטענו {len(df)} נכסים בהצלחה מתוך {total_assets} | שער USD/ILS: ₪{usd_to_ils:.3f}")
        
        if israeli_stocks:
            _manual_count = sum(
                1 for _v in israeli_stocks.values()
                if not (_v.get('fund_id') or _v.get('funder_id'))
                and _v.get('currency') != 'USD'
                and not _v.get('yf_ticker')
            )
            if _manual_count > 0:
                st.info(f"ℹ️ {_manual_count} נכסים ישראליים עם מחירים ידניים")

        # Baseline tracking — מבוסס על שווי השקעות בלבד (ללא מזומן) כדי שהוספת מזומן לא תיראה כרווח
        today = datetime.now().strftime('%Y-%m-%d')
        
        if db.baseline_exists():
            baseline_data = db.get_baseline()
            if not isinstance(baseline_data, dict):
                baseline_data = {}
            baseline_value = baseline_data.get('invested_value', baseline_data.get('value', total_invested))
            baseline_date = baseline_data.get('date', today)
        else:
            baseline_value = total_invested
            baseline_date = today
            if not db.save_baseline({'invested_value': total_invested, 'date': baseline_date}):
                st.warning("ערך הבסיס חושב אך לא נשמר; ההשוואה תחושב מחדש ברענון הבא.")
        
        if baseline_value > 0:
            pct_change = ((total_invested - baseline_value) / baseline_value) * 100
            ils_change = (total_invested_ils - baseline_value * usd_to_ils)
        else:
            pct_change = 0.0
            ils_change = 0.0

        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("שווי תיק כולל ($)", f"${total_value:,.2f}")
        col2.metric("שווי תיק כולל (₪)", f"₪{total_value_ils:,.2f}")
        
        # רווח כולל ($) — יחושב אחרי חישוב cost basis, כאן placeholder
        _pnl_placeholder = col3.empty()
        
        col4.metric("מספר פוזיציות", len(df))

        # ==================== NOTIFICATION HUB ====================
        try:
            alerts = []

            # --- 1) פקודות סטופ קרובות להפעלה ---
            _stops_for_banner = db.get_stop_orders(default_stop_orders.copy())
            for _tk, _sv in list(_stops_for_banner.items()):
                if isinstance(_sv, (int, float)):
                    _stops_for_banner[_tk] = {"stop_price": _sv, "currency": "USD"}
            for _tk, _si in _stops_for_banner.items():
                _row = df[df['Ticker'] == _tk]
                if _row.empty:
                    # maybe Israeli
                    if _tk in israeli_stocks and _tk not in ('CASH_USD', 'CASH_ILS'):
                        _cur_p = il_prices.get(_tk, israeli_stocks[_tk]['default_price_ils'])
                        _asset_cur = 'ILS'
                    else:
                        continue
                else:
                    _cur_p = float(_row.iloc[0]['Price'])
                    _asset_cur = 'USD'
                _stop_cur = _si.get('currency', 'USD')
                if _stop_cur == _asset_cur:
                    _cp = _cur_p
                elif _stop_cur == 'ILS' and _asset_cur == 'USD':
                    _cp = _cur_p * usd_to_ils
                else:
                    _cp = _cur_p / usd_to_ils
                _sp = _si['stop_price']
                if _cp > 0:
                    _dist = ((_cp - _sp) / _cp) * 100
                    # בדיקת ATR — מרחק < 2×ATR = קרוב
                    _banner_atr = calc_atr(history_data.get(_tk)) if _tk in history_data else None
                    _is_close = False
                    if _banner_atr is not None and _banner_atr > 0:
                        _b_atr = _banner_atr
                        if _stop_cur == 'ILS' and _asset_cur == 'USD':
                            _b_atr = _banner_atr * usd_to_ils
                        elif _stop_cur == 'USD' and _asset_cur == 'ILS':
                            _b_atr = _banner_atr / usd_to_ils
                        _b_ratio = (_cp - _sp) / _b_atr if _b_atr > 0 else 99
                        _is_close = _b_ratio < 2
                    else:
                        _is_close = _dist <= 5  # fallback אם אין ATR
                    if _is_close:
                        _sym = "₪" if _stop_cur == "ILS" else "$"
                        alerts.append(f"⚠️ סטופ **{_tk}** קרוב ({_dist:.1f}%) — מחיר: {_sym}{_cp:,.2f} ↔ סטופ: {_sym}{_sp:,.2f}")

            # --- 2) שיאי 52 שבועות ---
            us_tickers = tuple(portfolio.keys())
            notif_data = fetch_notification_data(us_tickers)
            for _tk, _nd in notif_data.items():
                if not _nd:
                    continue
                _high = _nd.get('52w_high')
                _row = df[df['Ticker'] == _tk]
                if _high and not _row.empty:
                    _cur_p = float(_row.iloc[0]['Price'])
                    if _cur_p >= _high * 0.98:  # תוך 2% מהשיא
                        _label = portfolio.get(_tk, {}).get('name', _tk)
                        alerts.append(f"📈 **{_label}** הגיע לשיא 52 שבועות! (${_cur_p:,.2f} / ${_high:,.2f})")

            # --- 3) חלוקת דיבידנד קרובה (ex-date בתוך 14 יום) ---
            from datetime import timedelta
            _now = datetime.now()
            for _tk, _nd in notif_data.items():
                if not _nd:
                    continue
                _exd = _nd.get('ex_div_date')
                if _exd:
                    try:
                        _ex_dt = datetime.fromtimestamp(_exd)
                        _days_left = (_ex_dt - _now).days
                        if 0 <= _days_left <= 14:
                            _label = portfolio.get(_tk, {}).get('name', _tk)
                            _div_rate = _nd.get('div_rate', 0)
                            _date_str = _ex_dt.strftime('%d/%m')
                            if _div_rate and _div_rate > 0:
                                alerts.append(f"💰 דיבידנד **{_label}** ב-{_date_str} (${_div_rate:.2f}/מניה)")
                            else:
                                alerts.append(f"💰 דיבידנד צפוי ב-**{_label}** ב-{_date_str}")
                    except:
                        pass

            # הצגת באנר
            if alerts:
                # בנה כרטיסיות HTML בודדות לכל התראה עם צבע לפי סוג
                cards_html = ""
                for a in alerts:
                    if a.startswith("⚠️"):
                        bg = "#2d1f00"
                        border = "#ffb300"
                        icon_color = "#ffb300"
                    elif a.startswith("📈"):
                        bg = "#002d1a"
                        border = "#00e676"
                        icon_color = "#00e676"
                    elif a.startswith("💰"):
                        bg = "#0d1f3c"
                        border = "#42a5f5"
                        icon_color = "#42a5f5"
                    else:
                        bg = "#1a1a2e"
                        border = "#888"
                        icon_color = "#ccc"
                    cards_html += (
                        f'<span style="display:inline-block; background:{bg}; '
                        f'border:1px solid {border}; border-radius:8px; '
                        f'padding:8px 18px; margin:0 12px; white-space:nowrap; '
                        f'font-size:14px; color:#f0f0f0; direction:rtl;">{a}</span>'
                    )

                # הכפל את הכרטיסיות כדי שהגלילה תהיה חלקה ואינסופית
                doubled = cards_html + cards_html

                st.markdown(f"""
                <style>
                @keyframes marquee-scroll {{
                    0%   {{ transform: translateX(0%); }}
                    100% {{ transform: translateX(-50%); }}
                }}
                .notif-track {{
                    overflow: hidden;
                    background: linear-gradient(90deg, rgba(15,15,30,0.95) 0%, rgba(22,33,62,0.95) 100%);
                    border-radius: 12px;
                    padding: 10px 0;
                    margin: 8px 0 4px 0;
                    position: relative;
                }}
                .notif-track::before, .notif-track::after {{
                    content: '';
                    position: absolute; top: 0; bottom: 0; width: 40px; z-index: 2;
                    pointer-events: none;
                }}
                .notif-track::before {{
                    left: 0;
                    background: linear-gradient(to right, rgba(15,15,30,1), transparent);
                }}
                .notif-track::after {{
                    right: 0;
                    background: linear-gradient(to left, rgba(22,33,62,1), transparent);
                }}
                .notif-scroll {{
                    display: inline-flex;
                    animation: marquee-scroll {max(len(alerts)*6, 15)}s linear infinite;
                }}
                .notif-scroll:hover {{
                    animation-play-state: paused;
                }}
                .notif-label {{
                    display: inline-block;
                    background: rgba(255,255,255,0.08);
                    border-radius: 8px;
                    padding: 8px 14px;
                    margin-left: 10px;
                    font-size: 13px;
                    font-weight: 700;
                    color: #ffd54f;
                    white-space: nowrap;
                    letter-spacing: 1px;
                }}
                </style>
                <div class="notif-track">
                    <div class="notif-scroll">
                        <span class="notif-label">🔔 התראות</span>
                        {doubled}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        except Exception:
            pass  # לא נכשיל את הדשבורד בגלל ההתראות

        st.divider()

        # ויזואליזציות
        df_grouped = df.groupby(['Name', 'Type'], as_index=False).agg({
            'Value': 'sum',
            'Value ILS': 'sum',
            'Quantity': 'sum'
        })
        
        st.subheader("⚖️ הקצאת נכסים (Asset Allocation)")
        fig_alloc = px.sunburst(df_grouped, path=['Type', 'Name'], values='Value', 
                                color='Type', title="חשיפה לפי אסטרטגיה")
        st.plotly_chart(fig_alloc, width='stretch')

        st.subheader("🏆 שווי אחזקות נוכחי")
        fig_bar = px.bar(df_grouped.sort_values('Value', ascending=False), 
                         x='Name', y='Value', color='Type', text_auto='.2s')
        st.plotly_chart(fig_bar, width='stretch')

        # --- הוספת מחיר רכישה ורווח/הפסד ---
        def _get_cost_basis_usd(ticker):
            """מחזיר מחיר רכישה בדולרים"""
            cb = cost_basis.get(ticker)
            if cb is None:
                return None
            if cb['currency'] == 'ILS':
                return cb['price'] / usd_to_ils
            return cb['price']
        
        df['Cost Basis'] = df['Ticker'].apply(lambda t: _get_cost_basis_usd(t))
        df['P&L %'] = df.apply(
            lambda row: ((row['Price'] - row['Cost Basis']) / row['Cost Basis'] * 100)
            if row['Cost Basis'] and row['Cost Basis'] > 0 else None, axis=1
        )
        df['P&L $'] = df.apply(
            lambda row: (row['Price'] - row['Cost Basis']) * row['Quantity']
            if row['Cost Basis'] and row['Cost Basis'] > 0 else None, axis=1
        )
        
        total_pnl = df['P&L $'].sum()
        total_cost = df.apply(
            lambda row: row['Cost Basis'] * row['Quantity'] if row['Cost Basis'] and row['Cost Basis'] > 0 else 0, axis=1
        ).sum()
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        
        # מילוי הרווח הכולל בראש הדף
        _pnl_placeholder.metric(
            "רווח כולל",
            f"${total_pnl:+,.2f} ({total_pnl_pct:+.2f}%)",
            delta=f"{total_pnl_pct:+.2f}%"
        )
        
        # --- רווח/הפסד יומי (Daily P&L) — ללא מזומן ---
        # prev close → current price, מתאפס כל יום אחרי סוף מסחר
        df['Daily Chg $'] = df.apply(
            lambda row: (row['Price'] - row['Prev Close']) * row['Quantity']
            if row['Type'] != 'Cash' and pd.notna(row.get('Prev Close')) and row['Prev Close'] > 0 else 0.0, axis=1
        )
        df['Daily Chg %'] = df.apply(
            lambda row: ((row['Price'] - row['Prev Close']) / row['Prev Close'] * 100)
            if row['Type'] != 'Cash' and pd.notna(row.get('Prev Close')) and row['Prev Close'] > 0 and row['Prev Close'] != row['Price'] else 0.0, axis=1
        )
        
        total_daily_pnl = df.loc[_invested_mask, 'Daily Chg $'].sum()
        total_daily_pnl_ils = total_daily_pnl * usd_to_ils
        # אחוז יומי כולל: שינוי ביחס לשווי השקעות אתמול (ללא מזומן)
        prev_total = df.loc[_invested_mask].apply(lambda row: row['Prev Close'] * row['Quantity'] if pd.notna(row.get('Prev Close')) and row['Prev Close'] > 0 else row['Value'], axis=1).sum()
        total_daily_pct = ((total_invested - prev_total) / prev_total * 100) if prev_total > 0 else 0.0

        # --- סקציית רווח/הפסד יומי בולטת ---
        _daily_color = "🟢" if total_daily_pnl >= 0 else "🔴"
        _daily_arrow = "▲" if total_daily_pnl >= 0 else "▼"
        
        st.subheader(f"📅 רווח/הפסד יומי {_daily_arrow}")
        
        dc1, dc2, dc3 = st.columns(3)
        dc1.metric(
            f"{_daily_color} שינוי יומי ($)",
            f"${total_daily_pnl:+,.2f}",
            delta=f"{total_daily_pct:+.2f}%"
        )
        dc2.metric(
            f"{_daily_color} שינוי יומי (₪)",
            f"₪{total_daily_pnl_ils:+,.2f}",
            delta=f"{total_daily_pct:+.2f}%"
        )
        dc3.metric("📊 שווי השקעות אתמול", f"${prev_total:,.2f}")
        
        # טבלת שינוי יומי לכל מניה — רק מניות עם שינוי (לא מזומן/ישראליות בלי נתון)
        daily_df = df[df['Daily Chg $'].abs() > 0.005].sort_values('Daily Chg $', ascending=True).copy()
        if not daily_df.empty:
            daily_display = daily_df[['Name', 'Ticker', 'Prev Close', 'Price', 'Quantity', 'Daily Chg %', 'Daily Chg $']].copy()
            daily_display.columns = ['שם', 'טיקר', 'סגירה אתמול ($)', 'מחיר נוכחי ($)', 'כמות', 'שינוי %', 'שינוי $']
            st.dataframe(
                daily_display.style.format({
                    'סגירה אתמול ($)': '${:.2f}',
                    'מחיר נוכחי ($)': '${:.2f}',
                    'כמות': '{:.2f}',
                    'שינוי %': '{:+.2f}%',
                    'שינוי $': '${:+,.2f}',
                }).map(
                    lambda v: 'color: #00c853' if isinstance(v, (int, float)) and v > 0 else ('color: #ff1744' if isinstance(v, (int, float)) and v < 0 else ''),
                    subset=['שינוי %', 'שינוי $']
                ),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("אין שינויים יומיים (השוק סגור או שאין נתוני מסחר)")
        
        st.divider()
        
        st.subheader("📋 פירוט נכסים")
        
        # KPI של רווח/הפסד כולל
        pnl_col1, pnl_col2, pnl_col3 = st.columns(3)
        pnl_col1.metric("💰 עלות רכישה כוללת", f"${total_cost:,.2f}")
        pnl_col2.metric("📈 רווח/הפסד כולל ($)", f"${total_pnl:,.2f}", delta=f"{total_pnl_pct:+.2f}%")
        pnl_col3.metric("📈 רווח/הפסד כולל (₪)", f"₪{total_pnl * usd_to_ils:,.2f}")
        
        df_display = df.sort_values('Value', ascending=False)
        # הסתר עמודות עזר מהטבלה הראשית
        _hide_cols = ['Prev Close']
        _show_cols = [c for c in df_display.columns if c not in _hide_cols]
        st.dataframe(df_display[_show_cols].style.format({
            "Price": "${:.2f}", 
            "Value": "${:.2f}",
            "Value ILS": "₪{:.2f}",
            "Portfolio %": "{:.2f}%",
            "Cost Basis": "${:.2f}",
            "P&L %": "{:+.2f}%",
            "P&L $": "${:+,.2f}",
            "Daily Chg %": "{:+.2f}%",
            "Daily Chg $": "${:+,.2f}",
        }).map(
            lambda v: 'color: #00c853' if isinstance(v, (int, float)) and v > 0 else ('color: #ff1744' if isinstance(v, (int, float)) and v < 0 else ''),
            subset=['P&L %', 'P&L $', 'Daily Chg %', 'Daily Chg $']
        ))
        
        st.subheader("📊 התפלגות לפי סוג נכס")
        type_summary = df.groupby('Type')['Value'].sum().sort_values(ascending=False)
        type_pct = (type_summary / total_value * 100).round(2)
        
        for asset_type in type_summary.index:
            type_value = type_summary[asset_type]
            type_percent = type_pct[asset_type]
            type_stocks = df[df['Type'] == asset_type].sort_values('Value', ascending=False)
            
            with st.expander(f"**{asset_type}** - ${type_value:,.2f} ({type_percent:.2f}% מהתיק)", expanded=False):
                st.write(f"**סה\"כ {len(type_stocks)} נכסים בקטגוריה זו**")
                
                type_display = type_stocks[['Name', 'Quantity', 'Price', 'Value', 'Portfolio %']].copy()
                type_display['% מהקטגוריה'] = (type_stocks['Value'] / type_value * 100).round(2)
                
                st.dataframe(type_display.style.format({
                    "Price": "${:.2f}",
                    "Value": "${:,.2f}",
                    "Portfolio %": "{:.2f}%",
                    "% מהקטגוריה": "{:.2f}%"
                }), width='stretch')
                
                fig_pie = px.pie(type_stocks, values='Value', names='Name', 
                                title=f'התפלגות בתוך {asset_type}')
                st.plotly_chart(fig_pie, width='stretch')

        # ==================== רכישת מניה ====================
        st.divider()
        st.subheader("📥 רכישת מניה")

        from datetime import date as _date_cls
        _purchase_records = db.get_purchased_stocks() or []
        if not isinstance(_purchase_records, list):
            _purchase_records = []
        _all_purchases = [p for p in _purchase_records if _is_valid_purchase_record(p)]

        _buy_cols1 = st.columns([2, 2, 1])
        with _buy_cols1[0]:
            _buy_ticker = normalize_market_ticker(
                st.text_input(
                    "טיקר (Ticker)",
                    placeholder="לדוגמה: AAPL (CNDX מזוהה אוטומטית כ-CNDX.L)",
                    key="buy_ticker",
                )
            )
        with _buy_cols1[1]:
            _buy_name = st.text_input("שם (אופציונלי)", placeholder="לדוגמה: Apple Inc.", key="buy_name").strip()
        with _buy_cols1[2]:
            _buy_type = st.selectbox("סוג", ["Satellite", "Core", "Crypto"], key="buy_type")

        _buy_cols2 = st.columns([2, 2, 2])
        with _buy_cols2[0]:
            _buy_qty = st.number_input("כמות מניות", min_value=0.0001, value=1.0, step=1.0, format="%.4f", key="buy_qty")
        with _buy_cols2[1]:
            _buy_price = st.number_input("מחיר רכישה ($)", min_value=0.001, value=100.0, step=0.01, format="%.3f", key="buy_price")
        with _buy_cols2[2]:
            _buy_date = st.date_input("תאריך רכישה", value=_date_cls.today(), key="buy_date")

        _buy_cols3 = st.columns([2, 2, 2])
        with _buy_cols3[0]:
            _buy_stop = st.number_input(
                "סטופ לוס ($) — אופציונלי", min_value=0.0, value=0.0, step=0.01, format="%.2f",
                key="buy_stop", help="השאר 0 אם אינך רוצה לקבוע סטופ"
            )
        with _buy_cols3[1]:
            _buy_total_cost = _buy_qty * _buy_price + TRADE_COMMISSION_USD
            st.metric("עלות כוללת + עמלה ($)", f"${_buy_total_cost:,.2f}")
        with _buy_cols3[2]:
            st.markdown("<br>", unsafe_allow_html=True)
            _buy_submit = st.button(
                "✅ שמור רכישה", key="buy_submit_btn", use_container_width=True,
                disabled=not bool(_buy_ticker)
            )

        if _buy_submit:
            if not _buy_ticker:
                st.error("חובה להזין טיקר.")
            elif _buy_qty <= 0:
                st.error("כמות חייבת להיות גדולה מ-0.")
            elif _buy_price <= 0:
                st.error("מחיר חייב להיות גדול מ-0.")
            else:
                _buy_name_final = _buy_name if _buy_name else _buy_ticker
                _buy_date_str = _buy_date.isoformat()
                _new_purchase = {
                    'id': uuid.uuid4().hex,
                    'ticker': _buy_ticker,
                    'name': _buy_name_final,
                    'type': _buy_type,
                    'qty': round(float(_buy_qty), 4),
                    'price': round(float(_buy_price), 4),
                    'currency': 'USD',
                    'date': _buy_date_str,
                    'stop_price': round(float(_buy_stop), 2) if _buy_stop > 0 else None,
                    'stop_currency': 'USD',
                    'commission_usd': TRADE_COMMISSION_USD,
                    'registered_at': datetime.now().isoformat(timespec='seconds'),
                }
                _existing_purchases = db.get_purchased_stocks() or []
                if not isinstance(_existing_purchases, list):
                    _existing_purchases = []
                _updated_purchases = list(_existing_purchases) + [_new_purchase]
                _purchase_save_steps = [
                    (db.save_purchased_stocks, _updated_purchases, _existing_purchases),
                ]
                # אם הוגדר סטופ — שמור אותו באותה פעולת מצב; כשל מחזיר את הרכישה לאחור.
                if _buy_stop > 0:
                    _old_stops_buy = db.get_stop_orders(default_stop_orders.copy()) or {}
                    _active_stops_buy = copy.deepcopy(_old_stops_buy)
                    _active_stops_buy[_buy_ticker] = {
                        'stop_price': round(float(_buy_stop), 2),
                        'currency': 'USD',
                        'check_from_ts': datetime.utcnow().isoformat(),
                    }
                    _purchase_save_steps.append(
                        (db.save_stop_orders, _active_stops_buy, _old_stops_buy)
                    )
                if _save_state_bundle(_purchase_save_steps):
                    st.success(
                        f"✅ נרשמה רכישה של **{_buy_ticker}** ({_buy_name_final}) — "
                        f"{_buy_qty:.4g} יח' × ${_buy_price:,.3f} = ${_buy_qty * _buy_price:,.2f}"
                        f" + עמלה ${TRADE_COMMISSION_USD:.2f}."
                        + (f" סטופ לוס: ${_buy_stop:,.2f}" if _buy_stop > 0 else "")
                    )
                    st.rerun()
                else:
                    st.error("שמירת הרכישה נכשלה; מצב הרכישות והסטופים הוחזר לאחור.")

        # טבלת רכישות שנרשמו
        if _all_purchases:
            with st.expander(f"📋 רכישות שנרשמו ({len(_all_purchases)})", expanded=True):
                _purch_rows = []
                for _p in reversed(_all_purchases):
                    _p_stop = f"${_p['stop_price']:,.2f}" if _p.get('stop_price') else "—"
                    _purch_rows.append({
                        'תאריך': _p.get('date', '—'),
                        'טיקר': _p['ticker'],
                        'שם': _p['name'],
                        'סוג': _p.get('type', '—'),
                        'כמות': _p['qty'],
                        'מחיר ($)': _p['price'],
                        'סטופ לוס': _p_stop,
                    })
                st.dataframe(pd.DataFrame(_purch_rows), hide_index=True, use_container_width=True)

                st.markdown("**ביטול רכישה שגויה (העברה לארכיון):**")
                _del_purch_opts = [
                    f"{_p['ticker']} | {_p.get('date','—')} | {_p['qty']} יח' @ ${_p['price']}"
                    for _p in _all_purchases
                ]
                _del_col1, _del_col2 = st.columns([4, 1])
                with _del_col1:
                    _del_purch_sel = st.selectbox("בחר רכישה למחיקה", _del_purch_opts, key="del_purch_sel")
                with _del_col2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    _selected_purchase = _all_purchases[_del_purch_opts.index(_del_purch_sel)]
                    _selected_purchase_ts = _record_timestamp(
                        _selected_purchase.get('date'), _selected_purchase.get('registered_at')
                    )
                    _linked_sale = any(
                        normalize_market_ticker(s.get('ticker')) == normalize_market_ticker(_selected_purchase.get('ticker'))
                        and _record_timestamp(s.get('date')) >= _selected_purchase_ts
                        for s in _sold_stocks if isinstance(s, dict)
                    )
                    if st.button(
                        "🗄️ ארכיון",
                        key="del_purch_btn",
                        use_container_width=True,
                        disabled=_linked_sale,
                    ):
                        _del_idx = _del_purch_opts.index(_del_purch_sel)
                        _selected_id = _all_purchases[_del_idx].get('id')
                        _source_idx = next(
                            (
                                idx for idx, item in enumerate(_purchase_records)
                                if (_selected_id and item.get('id') == _selected_id)
                                or (not _selected_id and item is _all_purchases[_del_idx])
                            ),
                            None,
                        )
                        if _source_idx is None:
                            st.error("לא ניתן לזהות את רשומת המקור; לא בוצע שינוי.")
                        else:
                            _archived_purchase = dict(_purchase_records[_source_idx])
                            _archived_purchase['id'] = _archived_purchase.get('id') or uuid.uuid4().hex
                            _archived_purchase['archived_at'] = datetime.now().isoformat(timespec='seconds')
                            _updated_purchase_records = list(_purchase_records)
                            _updated_purchase_records[_source_idx] = _archived_purchase
                            if db.save_purchased_stocks(_updated_purchase_records):
                                st.success(
                                    f"הרכישה {_archived_purchase['ticker']} {_archived_purchase.get('date','')} "
                                    "הועברה לארכיון ולא תיכלל בתיק או במזומן."
                                )
                                st.rerun()
                            else:
                                st.error("העברת הרכישה לארכיון נכשלה; הנתונים לא שונו.")
                    if _linked_sale:
                        st.caption("לא ניתן לבטל רכישה שמקושרת למכירה מאוחרת יותר.")

        # ==================== STOP MARKET ORDERS ====================
        try:
            st.divider()
            st.subheader("🛑 פקודות Stop Market")
            
            # טען פקודות סטופ פעילות וביצועים קודמים
            active_stops = db.get_stop_orders(copy.deepcopy(default_stop_orders)) or {}
            executed_history = db.get_executed_stops() or []
            if not isinstance(active_stops, dict):
                raise RuntimeError("נתוני הסטופים אינם תקינים; בדיקת הסטופים הופסקה")
            if not isinstance(executed_history, list):
                executed_history = []

            _active_position_tickers = set(portfolio) | {
                ticker for ticker, info in israeli_stocks.items()
                if info.get('type') != 'Cash'
            }

            # הרשימה השמורה היא הקובעת, גם כשהיא ריקה. ברירות המחדל משמשות
            # רק כשאין רשימה שמורה; אין לשחזר סטופים שבוטלו מתוך רכישות עבר.
            active_stops, _sync_needed = _normalize_active_stop_orders(
                active_stops, _active_position_tickers
            )

            # מיגרציה: המר check_from_date ישן ל-check_from_ts (חותמת זמן UTC מלאה).
            # סטופים שעודכנו ידנית ואין להם check_from_ts יקבלו ts=עכשיו,
            # כך שרק נרות מרגע זה ואילך יבדקו ל-Low.
            _retrofit_needed = False
            _now_utc_str = datetime.utcnow().isoformat()
            for _tk, _sv in list(active_stops.items()):
                if not isinstance(_sv, dict):
                    continue
                # הסר שדות ישנים של גרסאות קודמות
                _had_old = 'check_from_date' in _sv or 'low_check_from_date' in _sv
                _sv.pop('check_from_date', None)
                _sv.pop('low_check_from_date', None)
                if _had_old:
                    _retrofit_needed = True
                # אם הסטופ שונה מברירת המחדל ואין לו check_from_ts — צור אחד עכשיו
                if _tk in default_stop_orders and not _sv.get('check_from_ts'):
                    _def_sp = default_stop_orders[_tk].get('stop_price')
                    _cur_sp = _sv.get('stop_price')
                    if _def_sp is not None and _cur_sp is not None and float(_cur_sp) != float(_def_sp):
                        active_stops[_tk]['check_from_ts'] = _now_utc_str
                        _retrofit_needed = True
            
            # אם אין קובץ — שמור את ברירות המחדל
            if not db.stop_orders_file_exists() or _sync_needed or _retrofit_needed:
                if not db.save_stop_orders(active_stops):
                    raise RuntimeError("עדכון רשימת הסטופים לא נשמר; בדיקת הסטופים הופסקה")
            
            # בנה מיפוי של כל הנכסים (US + ישראליים) עם מחירים נוכחיים
            all_assets = {}
            for ticker_s, info_s in portfolio.items():
                row = df[df['Ticker'] == ticker_s]
                if not row.empty:
                    all_assets[ticker_s] = {
                        'name': info_s['name'],
                        'qty': float(info_s['qty']),
                        'current_price': float(row.iloc[0]['Price']),
                        'currency': 'USD'
                    }
            for ticker_s, info_s in israeli_stocks.items():
                if ticker_s in ('CASH_USD', 'CASH_ILS'):
                    continue
                price_ils = il_prices.get(ticker_s, info_s['default_price_ils'])
                all_assets[ticker_s] = {
                    'name': info_s['name'],
                    'qty': float(info_s['qty']),
                    'current_price': float(price_ils),
                    'currency': 'ILS'
                }
            
            # --- עדכון Trailing Stops ---
            _trailing_updated = False
            for ticker_s, stop_info in list(active_stops.items()):
                if stop_info.get('type') != 'trailing' or ticker_s not in all_assets:
                    continue
                asset = all_assets[ticker_s]
                trail_pct = stop_info.get('trail_pct', 5.0)
                stop_currency = stop_info.get('currency', 'USD')
                
                # מחיר נוכחי במטבע הסטופ
                if stop_currency == asset['currency']:
                    cp = asset['current_price']
                elif stop_currency == 'ILS' and asset['currency'] == 'USD':
                    cp = asset['current_price'] * usd_to_ils
                else:
                    cp = asset['current_price'] / usd_to_ils
                
                old_hwm = stop_info.get('high_watermark', cp)
                if cp > old_hwm:
                    # מחיר עלה — עדכן את ה-watermark ואת מחיר הסטופ
                    new_hwm = cp
                    old_stop = active_stops[ticker_s].get('stop_price')
                    new_stop = round(new_hwm * (1 - trail_pct / 100), 2)
                    active_stops[ticker_s]['high_watermark'] = round(new_hwm, 2)
                    active_stops[ticker_s]['stop_price'] = new_stop
                    # אחרי העלאת סטופ, בדיקת Low תתחיל רק מנרות שאחרי חותמת הזמן הנוכחית
                    if old_stop is None or new_stop != old_stop:
                        active_stops[ticker_s]['check_from_ts'] = datetime.utcnow().isoformat()
                    _trailing_updated = True
            
            if _trailing_updated:
                if not db.save_stop_orders(active_stops):
                    raise RuntimeError("עדכון ה-Trailing Stop לא נשמר; בדיקת הסטופים הופסקה")
            
            # בדוק כל פקודה פעילה מול מחיר נוכחי + Low intraday מסונן לפי שעת עדכון הסטופ
            newly_executed = []
            _today_str = datetime.now().strftime('%Y-%m-%d')
            for ticker_s, stop_info in list(active_stops.items()):
                if ticker_s not in all_assets:
                    continue

                # ביום הרכישה עצמו — לא בודקים סטופ
                _purchase_date = cost_basis.get(ticker_s, {}).get('date', '')
                if _purchase_date == _today_str:
                    continue

                asset = all_assets[ticker_s]
                stop_price = stop_info['stop_price']
                stop_currency = stop_info.get('currency', 'USD')
                
                # מחיר נוכחי במטבע הסטופ
                if stop_currency == asset['currency']:
                    current_price = asset['current_price']
                elif stop_currency == 'ILS' and asset['currency'] == 'USD':
                    current_price = asset['current_price'] * usd_to_ils
                else:
                    current_price = asset['current_price'] / usd_to_ils
                
                # --- Low intraday מסונן ---
                # אם עודכן סטופ תוך כדי יום, נסנן רק נרות שנצברו אחרי חותמת הזמן.
                # כך מכוסה גם המקרה בו האפליקציה הייתה סגורה — בפתיחה הנרות כבר שמורים.
                today_low_in_stop_cur = None
                _check_from_ts_str = stop_info.get('check_from_ts')
                _check_from_dt = None
                if _check_from_ts_str:
                    try:
                        _check_from_dt = datetime.fromisoformat(_check_from_ts_str)
                    except Exception:
                        pass

                _intraday_df = history_data.get(f"{ticker_s}__intraday")
                if _intraday_df is not None and not _intraday_df.empty:
                    _filtered = _intraday_df
                    if _check_from_dt is not None:
                        try:
                            _idx = _intraday_df.index
                            if hasattr(_idx, 'tz') and _idx.tz is not None:
                                import pytz as _pytz
                                _gate = _pytz.utc.localize(_check_from_dt) if _check_from_dt.tzinfo is None else _check_from_dt.astimezone(_pytz.utc)
                            else:
                                _gate = _check_from_dt
                            _filtered = _intraday_df[_intraday_df.index > _gate]
                        except Exception:
                            _filtered = _intraday_df
                    if not _filtered.empty:
                        _raw_low = float(_filtered['Low'].min())
                        if stop_currency == asset['currency']:
                            today_low_in_stop_cur = _raw_low
                        elif stop_currency == 'ILS' and asset['currency'] == 'USD':
                            today_low_in_stop_cur = _raw_low * usd_to_ils
                        else:
                            today_low_in_stop_cur = _raw_low / usd_to_ils
                
                # מחיר נוכחי: תמיד נבדק (אם המחיר כרגע ≤ סטופ — זה טריגר תקף)
                _triggered_by_current = current_price <= stop_price
                # Low: נבדק רק על נרות מסוננים שמאחרי check_from_ts
                _triggered_by_low = today_low_in_stop_cur is not None and today_low_in_stop_cur <= stop_price
                
                if _triggered_by_current or _triggered_by_low:
                    qty_s = asset['qty']
                    proceeds = qty_s * stop_price
                    symbol = "₪" if stop_currency == "ILS" else "$"
                    _trigger_reason = "Low של היום" if (not _triggered_by_current and _triggered_by_low) else "מחיר נוכחי"
                    _display_low = today_low_in_stop_cur if _triggered_by_low else None
                    
                    newly_executed.append({
                        'ticker': ticker_s,
                        'name': asset['name'],
                        'qty': qty_s,
                        'stop_price': stop_price,
                        'market_price': round(current_price, 2),
                        'today_low': round(_display_low, 2) if _display_low else None,
                        'trigger_reason': _trigger_reason,
                        'proceeds': round(proceeds, 2),
                        'currency': stop_currency,
                        'date': datetime.now().isoformat(timespec='seconds')
                    })
            
            # אם יש פקודות שהתממשו — הצג התראה
            if newly_executed:
                st.markdown("---")
                st.markdown("### 🚨 סטופ הופעל! אשר מכירה")
                
                _sale_prices = {}
                for idx_ex, ex in enumerate(newly_executed):
                    sym = "₪" if ex['currency'] == "ILS" else "$"
                    _trigger_info = ex.get('trigger_reason', 'מחיר נוכחי')
                    _low_str = f" | Low היום: {sym}{ex['today_low']:.2f}" if ex.get('today_low') else ""
                    st.error(
                        f"🚨 **STOP TRIGGERED: {ex['ticker']}** ({_trigger_info}) | "
                        f"מחיר שוק: {sym}{ex['market_price']:.2f} | סטופ: {sym}{ex['stop_price']:.2f}{_low_str} | "
                        f"{ex['qty']:.2f} יח' של {ex['name']}"
                    )
                    _sp_cols = st.columns([2, 2, 2])
                    with _sp_cols[0]:
                        st.metric("מחיר סטופ", f"{sym}{ex['stop_price']:.2f}")
                    with _sp_cols[1]:
                        _low_delta = f"Low: {sym}{ex['today_low']:.2f}" if ex.get('today_low') else None
                        st.metric("מחיר שוק נוכחי", f"{sym}{ex['market_price']:.2f}", delta=_low_delta, delta_color="off")
                    with _sp_cols[2]:
                        _actual_price = st.number_input(
                            f"💲 מחיר מכירה בפועל ({sym})",
                            min_value=0.01,
                            value=float(ex['market_price']),
                            step=0.01,
                            key=f"sale_price_{ex['ticker']}_{idx_ex}",
                            help="הכנס את המחיר שבו המניה נמכרה בפועל (יכול להיות שונה ממחיר הסטופ)"
                        )
                    _sale_prices[ex['ticker']] = _actual_price
                    _actual_proceeds = _actual_price * ex['qty']
                    st.info(f"💰 תמורה בפועל: **{sym}{_actual_proceeds:,.2f}** ({ex['qty']:.2f} × {sym}{_actual_price:.2f})")
                
                st.markdown("")
                if st.button("✅ אשר מכירות ועדכן תיק", key="confirm_stops"):
                    total_proceeds_usd = 0
                    total_proceeds_ils = 0
                    for ex in newly_executed:
                        t = ex['ticker']
                        actual_price = _sale_prices.get(t, ex['market_price'])
                        sold_entry = _record_sale(
                            db,
                            ticker=t,
                            name=ex['name'],
                            qty=ex['qty'],
                            sale_price=actual_price,
                            currency=ex['currency'],
                            sale_date=datetime.now().isoformat(timespec='seconds'),
                            stop_price=ex['stop_price'],
                            reason='stop',
                            fx_rate=usd_to_ils,
                        )
                        actual_proceeds = sold_entry['proceeds']
                        
                        if ex['currency'] == 'ILS':
                            total_proceeds_ils += actual_proceeds
                        else:
                            total_proceeds_usd += actual_proceeds
                    
                    msg = f"✅ בוצע! {len(newly_executed)} פקודות סטופ הופעלו.\n\n"
                    if total_proceeds_usd > 0:
                        msg += f"💵 תמורה בדולר: ${total_proceeds_usd:,.2f} — **נוסף למזומן**\n\n"
                    if total_proceeds_ils > 0:
                        msg += f"💰 תמורה בשקלים: ₪{total_proceeds_ils:,.2f} — **נוסף למזומן**\n\n"
                    msg += "🔄 התיק יתעדכן אוטומטית. רענן את הדף."
                    st.success(msg)
                    st.rerun()
            
            # טבלת סטטוס פקודות פעילות
            if active_stops:
                stop_rows = []
                for ticker_s, stop_info in active_stops.items():
                    if ticker_s not in all_assets:
                        continue
                    asset = all_assets[ticker_s]
                    stop_price = stop_info['stop_price']
                    stop_currency = stop_info.get('currency', 'USD')
                    sym = "₪" if stop_currency == "ILS" else "$"
                    
                    # מחיר נוכחי במטבע הסטופ
                    if stop_currency == asset['currency']:
                        current_price = asset['current_price']
                    elif stop_currency == 'ILS' and asset['currency'] == 'USD':
                        current_price = asset['current_price'] * usd_to_ils
                    else:
                        current_price = asset['current_price'] / usd_to_ils
                    
                    qty_s = asset['qty']
                    distance_pct = ((current_price - stop_price) / current_price * 100) if current_price > 0 else 0
                    
                    # רווח/הפסד מול מחיר רכישה אם הסטופ יתממש
                    cb = cost_basis.get(ticker_s)
                    if cb:
                        cb_price = cb['price']
                        cb_currency = cb['currency']
                        # המרה אם צריך — נביא cost basis למטבע הסטופ
                        if cb_currency == stop_currency:
                            cb_in_stop_currency = cb_price
                        elif cb_currency == 'ILS' and stop_currency == 'USD':
                            cb_in_stop_currency = cb_price / usd_to_ils
                        else:  # cb_currency == 'USD' and stop_currency == 'ILS'
                            cb_in_stop_currency = cb_price * usd_to_ils
                        # רווח כרגע = (מחיר נוכחי - מחיר קנייה) × כמות
                        current_pnl = qty_s * (current_price - cb_in_stop_currency)
                        current_pnl_str = f"{sym}{current_pnl:+,.2f}"
                        # רווח/הפסד אם הסטופ יתממש = (מחיר סטופ - מחיר קנייה) × כמות
                        pnl_vs_cost = qty_s * (stop_price - cb_in_stop_currency)
                        pnl_vs_cost_str = f"{sym}{pnl_vs_cost:+,.2f}"
                    else:
                        current_pnl_str = "—"
                    # חישוב ATR לקביעת סטטוס (מרחק < 2×ATR = קרוב)
                    _atr_val = None
                    _atr_str = "—"
                    if ticker_s in history_data:
                        _atr_val = calc_atr(history_data[ticker_s])
                    if _atr_val is not None and _atr_val > 0:
                        # ATR ביחידות USD — אם הסטופ ב-ILS צריך להמיר
                        if stop_currency == 'ILS' and asset['currency'] == 'USD':
                            atr_in_stop_cur = _atr_val * usd_to_ils
                        elif stop_currency == 'USD' and asset['currency'] == 'ILS':
                            atr_in_stop_cur = _atr_val / usd_to_ils
                        else:
                            atr_in_stop_cur = _atr_val
                        distance_abs = current_price - stop_price
                        atr_ratio = distance_abs / atr_in_stop_cur if atr_in_stop_cur > 0 else 99
                        _atr_str = f"{sym}{atr_in_stop_cur:,.2f} ({atr_ratio:.1f}×)"
                        if atr_ratio < 1:
                            status = "🔴 קרוב מאוד!"
                        elif atr_ratio < 2:
                            status = "🟡 מתקרב"
                        else:
                            status = "🟢 בטוח"
                    else:
                        # fallback — אין ATR (נכס ישראלי ללא היסטוריה)
                        if distance_pct <= 2:
                            status = "🔴 קרוב מאוד!"
                        elif distance_pct <= 5:
                            status = "🟡 מתקרב"
                        else:
                            status = "🟢 בטוח"
                    
                    stop_rows.append({
                        'סטטוס': status,
                        'טיקר': ticker_s,
                        'שם': asset['name'],
                        'סוג': f"📉 Trailing {stop_info['trail_pct']}%" if stop_info.get('type') == 'trailing' else "🛑 Stop",
                        'כמות': f"{qty_s:.2f}",
                        'מחיר קנייה': f"{sym}{cb_in_stop_currency:,.2f}" if cb else "—",
                        'מחיר נוכחי': f"{sym}{current_price:,.2f}",
                        'מחיר סטופ': f"{sym}{stop_price:,.2f}",
                        'ATR(14)': _atr_str,
                        'מרחק': f"{distance_pct:.1f}%",
                        'רווח כרגע': current_pnl_str,
                        'רווח/הפסד במימוש': pnl_vs_cost_str,
                    })
                
                if stop_rows:
                    stop_df = pd.DataFrame(stop_rows)
                    st.dataframe(stop_df, hide_index=True)
                
                # --- עריכת מחיר סטופ ---
                st.markdown("**✏️ עריכת מחיר סטופ:**")
                _edit_cols = st.columns([2, 2, 2, 1])
                _stop_tickers = [t for t in active_stops if t in all_assets]
                with _edit_cols[0]:
                    _edit_stop_ticker = st.selectbox(
                        "בחר נכס",
                        _stop_tickers,
                        format_func=lambda t: f"{t} — {all_assets[t]['name']}",
                        key="edit_stop_ticker"
                    )
                if _edit_stop_ticker:
                    _cur_stop = active_stops[_edit_stop_ticker]
                    _stop_sym = "₪" if _cur_stop.get('currency', 'USD') == 'ILS' else "$"
                    with _edit_cols[1]:
                        st.metric("מחיר סטופ נוכחי", f"{_stop_sym}{_cur_stop['stop_price']:,.2f}")
                    with _edit_cols[2]:
                        _new_stop_price = st.number_input(
                            f"מחיר סטופ חדש ({_stop_sym})",
                            min_value=0.01,
                            value=float(_cur_stop['stop_price']),
                            step=1.0,
                            key="new_stop_price"
                        )
                    with _edit_cols[3]:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("💾 עדכן", key="update_stop_btn", use_container_width=True):
                            _updated_stops = copy.deepcopy(active_stops)
                            _updated_stops[_edit_stop_ticker]['stop_price'] = round(_new_stop_price, 2)
                            # בדיקת Low תסנן רק נרות שנצברו אחרי רגע זה
                            _updated_stops[_edit_stop_ticker]['check_from_ts'] = datetime.utcnow().isoformat()
                            if db.save_stop_orders(_updated_stops):
                                st.success(f"✅ סטופ {_edit_stop_ticker} עודכן ל-{_stop_sym}{_new_stop_price:,.2f}")
                                st.rerun()
                            else:
                                st.error("עדכון הסטופ לא נשמר; המחיר הקודם נשאר פעיל.")
            else:
                st.info("אין פקודות סטופ פעילות.")

            st.markdown("**💸 רישום מכירה ידנית:**")
            _manual_sale_tickers = [t for t in all_assets if t not in ('CASH_USD', 'CASH_ILS')]
            if _manual_sale_tickers:
                _manual_cols = st.columns([2, 1, 1, 1])
                with _manual_cols[0]:
                    _manual_ticker = st.selectbox(
                        "בחר נכס למכירה",
                        _manual_sale_tickers,
                        format_func=lambda t: f"{t} — {all_assets[t]['name']}",
                        key="manual_sale_ticker"
                    )
                _manual_asset = all_assets[_manual_ticker]
                _manual_sym = "₪" if _manual_asset['currency'] == 'ILS' else "$"
                with _manual_cols[1]:
                    st.metric("כמות למכירה", f"{_manual_asset['qty']:.2f}")
                with _manual_cols[2]:
                    _manual_sale_price = st.number_input(
                        f"מחיר מכירה ({_manual_sym})",
                        min_value=0.01,
                        value=float(_manual_asset['current_price']),
                        step=0.01,
                        key="manual_sale_price"
                    )
                with _manual_cols[3]:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🧾 רשום מכירה", key="record_manual_sale", use_container_width=True):
                        _manual_stop = active_stops.get(_manual_ticker, {}).get('stop_price')
                        _manual_entry = _record_sale(
                            db,
                            ticker=_manual_ticker,
                            name=_manual_asset['name'],
                            qty=_manual_asset['qty'],
                            sale_price=_manual_sale_price,
                            currency=_manual_asset['currency'],
                            sale_date=datetime.now().isoformat(timespec='seconds'),
                            stop_price=_manual_stop,
                            reason='manual',
                            fx_rate=usd_to_ils,
                        )
                        st.success(
                            f"✅ נרשמה מכירה של {_manual_ticker} במחיר {_manual_sym}{_manual_sale_price:,.2f}. "
                            f"המזומן עודכן ב-{_manual_sym}{_manual_entry['proceeds']:,.2f}."
                        )
                        st.rerun()
            else:
                st.info("אין נכסים זמינים לרישום מכירה ידנית.")

            # היסטוריית מכירות ממומשות
            if executed_history:
                with st.expander(f"📜 היסטוריית מכירות שבוצעו ({len(executed_history)})", expanded=False):
                    hist_rows = []
                    total_realized_pnl_usd = 0.0
                    total_realized_pnl_ils = 0.0
                    for ex in reversed(executed_history):
                        if not isinstance(ex, dict) or not ex.get('ticker'):
                            continue
                        _is_ils = ex.get('currency') == "ILS"
                        sym = "₪" if _is_ils else "$"
                        try:
                            _sale_p = float(ex.get('sale_price', ex.get('market_price', ex.get('stop_price'))))
                            _qty = float(ex.get('qty', 0))
                            _commission = float(ex.get('commission_usd', 0.0) or 0.0)
                        except (TypeError, ValueError):
                            continue
                        if _sale_p <= 0 or _qty <= 0:
                            continue
                        _gross_proceeds = _sale_p * _qty
                        _stored_proceeds = ex.get('proceeds')
                        if _stored_proceeds is None:
                            _proceeds = round(_gross_proceeds - (_commission if not _is_ils else 0.0), 2)
                        else:
                            try:
                                _stored_proceeds = float(_stored_proceeds)
                            except (TypeError, ValueError):
                                _stored_proceeds = None
                            if _stored_proceeds is None:
                                _proceeds = round(_gross_proceeds - (_commission if not _is_ils else 0.0), 2)
                            elif (not _is_ils) and _commission and abs(_stored_proceeds - _gross_proceeds) < 0.02:
                                _proceeds = round(_stored_proceeds - _commission, 2)
                            else:
                                _proceeds = _stored_proceeds
                        # חישוב רווח/הפסד — קודם מהרשומה עצמה, אחרת מה-cost_basis
                        _cost_per = ex.get('cost_per_share')
                        if _cost_per is None:
                            _cb = cost_basis.get(ex['ticker'])
                            _cost_per = _cb['price'] if _cb else None
                        if _cost_per:
                            try:
                                _cost_per = float(_cost_per)
                            except (TypeError, ValueError):
                                _cost_per = None
                        if _cost_per and _cost_per > 0:
                            _total_cost = _cost_per * _qty
                            _commission_in_trade_currency = 0.0
                            if _is_ils:
                                try:
                                    _commission_in_trade_currency = float(ex.get('commission_ils') or 0.0)
                                except (TypeError, ValueError):
                                    _commission_in_trade_currency = 0.0
                            _pnl = _proceeds - _total_cost - _commission_in_trade_currency
                            _pnl_pct = (_pnl / _total_cost * 100) if _total_cost > 0 else 0
                            _pnl_str = f"{sym}{_pnl:+,.2f} ({_pnl_pct:+.1f}%)"
                            _cost_str = f"{sym}{_cost_per:,.2f}"
                            if _is_ils:
                                total_realized_pnl_ils += _pnl
                            else:
                                total_realized_pnl_usd += _pnl
                        else:
                            _pnl_str = "—"
                            _cost_str = "—"
                        
                        hist_rows.append({
                            'תאריך': ex.get('date', '—'),
                            'טיקר': ex['ticker'],
                            'שם': ex.get('name', '—'),
                            'סוג': '🛑 סטופ' if ex.get('reason') == 'stop' else '💸 ידני',
                            'כמות': f"{_qty:.0f}",
                            'עלות רכישה': _cost_str,
                            'מחיר סטופ': f"{sym}{ex['stop_price']:,.2f}" if ex.get('stop_price') is not None else "—",
                            'מחיר מכירה': f"{sym}{_sale_p:,.2f}",
                            'תמורה': f"{sym}{_proceeds:,.2f}",
                            'רווח/הפסד': _pnl_str,
                        })
                    
                    if hist_rows:
                        st.dataframe(pd.DataFrame(hist_rows), hide_index=True, use_container_width=True)
                        
                        # סיכום כולל — רווח/הפסד ממומש בלבד
                        _pnl_color_usd = "🟢" if total_realized_pnl_usd >= 0 else "🔴"
                        hc1, hc2 = st.columns(2)
                        hc1.metric(f"{_pnl_color_usd} רווח/הפסד ממומש ($)", f"${total_realized_pnl_usd:+,.2f}")
                        hc2.metric("📊 עסקאות", f"{len(executed_history)}")
                        if total_realized_pnl_ils != 0:
                            _pnl_color_ils = "🟢" if total_realized_pnl_ils >= 0 else "🔴"
                            hc3, hc4 = st.columns(2)
                            hc3.metric(f"{_pnl_color_ils} רווח/הפסד ממומש (₪)", f"₪{total_realized_pnl_ils:+,.2f}")
                            hc4.metric("", "")
        except Exception as e:
            st.error(f"⚠️ שגיאה בסקציית סטופ: {e}")
        

        st.divider()

        # ==================== הכנסה פסיבית מדיבידנדים ====================
        st.subheader("💰 הכנסה פסיבית מדיבידנדים")

        # ערכי seed בלבד — ישמשו fallback לנכסים שלא עודכנו עדיין מה-API
        _seed_dividends = {
            "IEFA":   3.178,
            "IEMG":   1.849,
            "MSFT":   3.56,
            "SFL":    0.47,
            "BKR":    0.92,
            "NVDA":   0.04,
            "LIN":    6.10,
            "PPA":    0.656,
        }

        # רשימת כל הטיקרים הנוכחיים בתיק (US בלבד — לא ישראליים ולא מזומן)
        _current_us_tickers = tuple(t for t in portfolio if t not in israeli_stocks)

        # כפתור עדכון — שולח את כל הטיקרים הנוכחיים (לא רק ה-seed)
        div_col1, div_col2 = st.columns([1, 4])
        with div_col1:
            update_div = st.button("🔄 עדכן דיבידנדים", help="משיכת נתוני דיבידנד עדכניים מ-yfinance (לוקח ~30 שניות)")

        if update_div:
            with st.spinner("⏳ מושך נתוני דיבידנד עדכניים..."):
                fetch_live_dividends.clear()
                fetch_notification_data.clear()
                live = fetch_live_dividends(_current_us_tickers)
                _live_notifications = fetch_notification_data(_current_us_tickers)
            if live:
                _new_dividend_snapshot = {
                    "rates": live,
                    "notifications": {
                        ticker: {
                            "ex_div_date": details.get("ex_div_date"),
                            "div_date": details.get("div_date"),
                        }
                        for ticker, details in _live_notifications.items()
                    },
                    "tickers": list(_current_us_tickers),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "source": "yfinance",
                }
                if db.save_dividend_snapshot(_new_dividend_snapshot):
                    with div_col2:
                        st.success(f"✅ נשמרו נתוני דיבידנד עבור {len(live)} נכסים.")
                else:
                    with div_col2:
                        st.error("הנתונים נמשכו אך השמירה נכשלה; הטבלה הקודמת נשארה זמינה.")
            else:
                with div_col2:
                    st.warning("⚠️ לא הצליח לעדכן")

        # בנה known_dividends:
        # 1. seed רק לנכסים שעדיין בתיק
        # 2. live data שנשמרה ב-DB בעדיפות (לא נדרש רענון בכל פעם)
        _base_div = {k: v for k, v in _seed_dividends.items() if k in portfolio}
        _dividend_snapshot = db.get_dividend_snapshot() or {}
        if not isinstance(_dividend_snapshot, dict):
            _dividend_snapshot = {}
        _saved_live_divs = _dividend_snapshot.get('rates', {})
        # תאימות לנתונים שנשמרו בעבר בתוך מצב המזומן — ללא שינוי או מחיקה שלהם.
        if not _saved_live_divs:
            _saved_live_divs = _saved_deposits.get('saved_dividends', {})
        if _saved_live_divs:
            _live_for_portfolio = {k: v for k, v in _saved_live_divs.items() if k in portfolio}
            known_dividends = {**_base_div, **_live_for_portfolio}
        else:
            known_dividends = _base_div

        div_rows = []
        total_annual_div_usd = 0

        # תאריכי Ex/תשלום מגיעים מה-snapshot השמור ומתעדכנים רק בלחיצה.
        _div_notif = _dividend_snapshot.get('notifications', {})

        for ticker, div_per_share in known_dividends.items():
            if div_per_share <= 0:
                continue
            asset_row = df[df['Ticker'] == ticker]
            if asset_row.empty:
                continue

            price = float(asset_row['Price'].iloc[0])
            qty = portfolio[ticker]['qty']
            info = portfolio[ticker]

            annual_income = div_per_share * qty
            actual_yield = div_per_share / price * 100 if price > 0 else 0

            total_annual_div_usd += annual_income

            # תאריך Ex-Dividend ותאריך תשלום
            _ex_date_str  = "לא ידוע"
            _pay_date_str = "לא ידוע"
            _ex_ts  = _div_notif.get(ticker, {}).get('ex_div_date')
            _pay_ts = _div_notif.get(ticker, {}).get('div_date')
            if _ex_ts:
                try:
                    _ex_dt = datetime.fromtimestamp(_ex_ts)
                    _days = (_ex_dt - datetime.now()).days
                    _date_fmt = _ex_dt.strftime('%d/%m/%Y')
                    if _days > 0:
                        _ex_date_str = f"{_date_fmt} (בעוד {_days} ימים)"
                    elif _days == 0:
                        _ex_date_str = f"{_date_fmt} (היום!)"
                    else:
                        _ex_date_str = f"{_date_fmt} (עבר)"
                except Exception:
                    pass
            if _pay_ts:
                try:
                    _pay_dt = datetime.fromtimestamp(_pay_ts)
                    _pdays = (_pay_dt - datetime.now()).days
                    _pay_fmt = _pay_dt.strftime('%d/%m/%Y')
                    if _pdays > 0:
                        _pay_date_str = f"{_pay_fmt} (בעוד {_pdays} ימים)"
                    elif _pdays == 0:
                        _pay_date_str = f"{_pay_fmt} (היום!)"
                    else:
                        _pay_date_str = f"{_pay_fmt} (עבר)"
                except Exception:
                    pass

            div_rows.append({
                'שם': info['name'],
                'טיקר': ticker,
                'Yield (%)': actual_yield,
                'דיבידנד שנתי למניה ($)': div_per_share,
                'הכנסה שנתית ($)': annual_income,
                'הכנסה שנתית (₪)': annual_income * usd_to_ils,
                'Ex-Dividend': _ex_date_str,
                'תאריך תשלום': _pay_date_str,
            })

        if div_rows:
            div_df = pd.DataFrame(div_rows).sort_values('הכנסה שנתית ($)', ascending=False)

            weighted_yield = (total_annual_div_usd / total_value * 100) if total_value > 0 else 0
            annual_ils = total_annual_div_usd * usd_to_ils
            monthly_ils = annual_ils / 12

            dcol1, dcol2, dcol3, dcol4 = st.columns(4)
            dcol1.metric("🎯 Yield משוקלל של התיק", f"{weighted_yield:.2f}%")
            dcol2.metric("💵 הכנסה שנתית ($)", f"${total_annual_div_usd:,.2f}")
            dcol3.metric("💰 הכנסה שנתית (₪)", f"₪{annual_ils:,.0f}")
            dcol4.metric("📅 הכנסה חודשית (₪)", f"₪{monthly_ils:,.0f}")

            st.dataframe(
                div_df.style.format({
                    'Yield (%)': '{:.2f}%',
                    'דיבידנד שנתי למניה ($)': '${:.4f}',
                    'הכנסה שנתית ($)': '${:,.2f}',
                    'הכנסה שנתית (₪)': '₪{:,.0f}',
                }),
                width='stretch'
            )

            # הערה דינמית — מחשב בזמן אמת אילו נכסים לא מחלקים דיבידנד
            _div_paying = {t for t in known_dividends if known_dividends[t] > 0 and t in portfolio}
            _non_div = [t for t in _current_us_tickers if t not in _div_paying]
            if _non_div:
                _non_div_names = ", ".join(
                    portfolio[t]['name'] for t in _non_div[:8]
                ) + ("..." if len(_non_div) > 8 else "")
                st.caption(f"ℹ️ {len(_non_div)} נכסים בתיק לא מחלקים דיבידנד: {_non_div_names}.")
            st.caption("💡 לחץ '🔄 עדכן דיבידנדים' לקבלת נתונים עדכניים מ-yfinance עבור כל הנכסים הנוכחיים בתיק.")
            _div_updated_at = _dividend_snapshot.get('updated_at')
            if _div_updated_at:
                st.caption(f"עדכון אחרון שנשמר: {_div_updated_at}")
            st.caption("ℹ️ הטבלה היא למעקב בלבד. קבלת דיבידנד אינה משנה מזומן אוטומטית; הפקדה מתבצעת ידנית בסרגל הצד.")

        else:
            st.info("לא נמצאו נכסים מחלקי דיבידנד בתיק.")

        # ==================== השוואה מול השוק ====================
        st.subheader("📈 האם ניצחתי את השוק?")
        
        try:
            # === חלק 1: תשואה כוללת מבוססת Cost Basis (תמיד עובד!) ===
            st.markdown("#### 🏦 תשואה כוללת מאז הרכישה")
            
            # חישוב עלות ושווי נוכחי של כל התיק
            total_cost_usd = 0.0
            total_value_usd = 0.0
            ticker_returns = []
            
            usd_ils = get_usd_to_ils()
            
            # מניות אמריקאיות
            for ticker, info in portfolio.items():
                cb = cost_basis.get(ticker)
                if cb and cb['currency'] == 'USD':
                    buy_price = cb['price']
                    qty = info['qty']
                    cost = buy_price * qty
                    # מחיר נוכחי מה-DataFrame שכבר נטען
                    current_row = df[df['Ticker'] == ticker]
                    if not current_row.empty:
                        current_price = float(current_row['Price'].iloc[0])
                        value = current_price * qty
                        pnl_pct = (current_price - buy_price) / buy_price * 100
                        total_cost_usd += cost
                        total_value_usd += value
                        ticker_returns.append({
                            'נכס': f"{info['name']} ({ticker})",
                            'עלות ($)': cost,
                            'שווי נוכחי ($)': value,
                            'תשואה %': pnl_pct,
                            'רווח/הפסד ($)': value - cost,
                            'משקל בתיק %': 0  # ימולא אחרי
                        })
            
            # מניות ישראליות (המרה לדולר)
            for il_ticker, il_info in israeli_stocks.items():
                cb = cost_basis.get(il_ticker)
                if cb and cb['currency'] == 'ILS' and il_ticker not in ('CASH_USD', 'CASH_ILS'):
                    buy_price_ils = cb['price']
                    qty = il_info['qty']
                    cost_ils = buy_price_ils * qty
                    current_price_ils = il_info['default_price_ils']
                    value_ils = current_price_ils * qty
                    pnl_pct = (current_price_ils - buy_price_ils) / buy_price_ils * 100
                    
                    cost_usd = cost_ils / usd_ils
                    value_usd = value_ils / usd_ils
                    total_cost_usd += cost_usd
                    total_value_usd += value_usd
                    ticker_returns.append({
                        'נכס': f"{il_info['name']} ({il_ticker})",
                        'עלות ($)': cost_usd,
                        'שווי נוכחי ($)': value_usd,
                        'תשואה %': pnl_pct,
                        'רווח/הפסד ($)': value_usd - cost_usd,
                        'משקל בתיק %': 0
                    })
            
            # אותו חישוב מזומן קנוני שמשמש בטבלה הראשית.
            cash_usd = _cash_balance_usd(
                base_cash_usd=israeli_stocks.get('CASH_USD', {}).get('qty', 0),
                cash_state=_saved_deposits,
                purchase_deductions_usd=_purchase_deductions_usd,
                usd_to_ils=usd_ils,
            )
            total_cost_usd += cash_usd
            total_value_usd += cash_usd
            
            # חישוב תשואת התיק הכוללת
            my_total_return = ((total_value_usd - total_cost_usd) / total_cost_usd) * 100 if total_cost_usd > 0 else 0
            my_total_pnl = total_value_usd - total_cost_usd
            
            # עדכון משקלות
            for tr in ticker_returns:
                tr['משקל בתיק %'] = (tr['שווי נוכחי ($)'] / total_value_usd * 100) if total_value_usd > 0 else 0
            
            # KPIs ראשיים
            kcol1, kcol2, kcol3, kcol4 = st.columns(4)
            kcol1.metric("💰 סה\"כ עלות", f"${total_cost_usd:,.0f}")
            kcol2.metric("📊 שווי נוכחי", f"${total_value_usd:,.0f}")
            kcol3.metric("📈 תשואה כוללת", f"{my_total_return:+.2f}%")
            kcol4.metric("💵 רווח/הפסד", f"${my_total_pnl:+,.0f}")
            
            # טבלת תשואה לכל נכס
            if ticker_returns:
                returns_df = pd.DataFrame(ticker_returns).sort_values('תשואה %', ascending=False)
                returns_df['עלות ($)'] = returns_df['עלות ($)'].map(lambda x: f"${x:,.0f}")
                returns_df['שווי נוכחי ($)'] = returns_df['שווי נוכחי ($)'].map(lambda x: f"${x:,.0f}")
                returns_df['רווח/הפסד ($)'] = returns_df['רווח/הפסד ($)'].map(lambda x: f"${x:+,.0f}")
                returns_df['תשואה %'] = returns_df['תשואה %'].map(lambda x: f"{x:+.2f}%")
                returns_df['משקל בתיק %'] = returns_df['משקל בתיק %'].map(lambda x: f"{x:.1f}%")
                st.dataframe(returns_df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # === חלק 2: השוואה מנורמלת מול מדדים (גרף) ===
            st.markdown("#### 📉 ביצועים מול מדדים לאורך זמן")
            
            period_choice = st.selectbox("בחר תקופה להשוואה:", 
                                         ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
                                         index=3,
                                         format_func=lambda x: {"1mo": "חודש", "3mo": "3 חודשים", "6mo": "6 חודשים", "1y": "שנה", "2y": "שנתיים", "5y": "5 שנים"}[x])
            
            # משיכת נתוני מדדים
            spy_hist = yf.Ticker("SPY").history(period=period_choice)
            vt_hist = yf.Ticker("VT").history(period=period_choice)
            
            # חישוב ביצועי התיק - רק טיקרים שעובדים
            portfolio_daily = pd.DataFrame()
            working_tickers = []
            failed_tickers = []
            for ticker, info in portfolio.items():
                try:
                    hist = yf.Ticker(ticker).history(period=period_choice)
                    if not hist.empty and len(hist) > 1:
                        portfolio_daily[ticker] = hist['Close'] * info['qty']
                        working_tickers.append(ticker)
                    else:
                        failed_tickers.append(ticker)
                except:
                    failed_tickers.append(ticker)
            
            if not portfolio_daily.empty and not spy_hist.empty:
                # חישוב שווי תיק יומי (ללא dropna - נמלא חסרים)
                portfolio_daily = portfolio_daily.ffill().bfill()
                portfolio_total = portfolio_daily.sum(axis=1)
                
                # נרמול ל-100
                portfolio_norm = (portfolio_total / portfolio_total.iloc[0]) * 100
                spy_norm = (spy_hist['Close'] / spy_hist['Close'].iloc[0]) * 100
                
                # יצירת DataFrame משולב - reindex לפי תאריכי SPY (המדד האמין ביותר)
                comparison = pd.DataFrame(index=spy_norm.index)
                comparison['S&P 500 (SPY)'] = spy_norm
                
                # יישור התיק לאותם תאריכים
                portfolio_reindexed = portfolio_norm.reindex(comparison.index, method='nearest')
                comparison['התיק שלי'] = portfolio_reindexed
                
                if not vt_hist.empty:
                    vt_norm = (vt_hist['Close'] / vt_hist['Close'].iloc[0]) * 100
                    vt_reindexed = vt_norm.reindex(comparison.index, method='nearest')
                    comparison['עולמי (VT)'] = vt_reindexed
                
                comparison = comparison.dropna()
                
                if not comparison.empty:
                    # חישוב תשואות לתקופה
                    period_my_return = comparison['התיק שלי'].iloc[-1] - 100
                    period_spy_return = comparison['S&P 500 (SPY)'].iloc[-1] - 100
                    period_vt_return = comparison['עולמי (VT)'].iloc[-1] - 100 if 'עולמי (VT)' in comparison.columns else None
                    
                    # KPIs של השוואה
                    pcol1, pcol2, pcol3 = st.columns(3)
                    pcol1.metric("📊 התיק שלי (תקופה)", f"{period_my_return:+.2f}%")
                    pcol2.metric("🇺🇸 S&P 500", f"{period_spy_return:+.2f}%", 
                                delta=f"{'ניצחת! 🎉' if period_my_return > period_spy_return else 'פיגור'} ({period_my_return - period_spy_return:+.2f}%)")
                    if period_vt_return is not None:
                        pcol3.metric("🌍 עולמי (VT)", f"{period_vt_return:+.2f}%",
                                    delta=f"{'ניצחת! 🎉' if period_my_return > period_vt_return else 'פיגור'} ({period_my_return - period_vt_return:+.2f}%)")
                    
                    # גרף השוואה מנורמל
                    import plotly.graph_objects as go
                    fig_compare = go.Figure()
                    fig_compare.add_trace(go.Scatter(x=comparison.index, y=comparison['התיק שלי'], 
                                                      name='התיק שלי', line=dict(color='#00cc96', width=3)))
                    fig_compare.add_trace(go.Scatter(x=comparison.index, y=comparison['S&P 500 (SPY)'], 
                                                      name='S&P 500', line=dict(color='#636efa', width=2, dash='dash')))
                    if 'עולמי (VT)' in comparison.columns:
                        fig_compare.add_trace(go.Scatter(x=comparison.index, y=comparison['עולמי (VT)'], 
                                                          name='עולמי (VT)', line=dict(color='#ef553b', width=2, dash='dot')))
                    
                    fig_compare.add_hline(y=100, line_dash="solid", line_color="gray", opacity=0.4, 
                                           annotation_text="נקודת התחלה (100)")
                    fig_compare.update_layout(
                        title=f"ביצועים מנורמלים - התיק שלי מול השוק ({period_choice})",
                        yaxis_title="ביצועים מנורמלים (בסיס=100)",
                        xaxis_title="תאריך",
                        hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_compare, width='stretch')
                    
                    # הודעת סיכום
                    if period_my_return > period_spy_return and (period_vt_return is None or period_my_return > period_vt_return):
                        st.success(f"🏆 מזל טוב! ניצחת את השוק בתקופה הנבחרת! התיק שלך עלה {period_my_return:+.2f}% לעומת S&P 500 {period_spy_return:+.2f}%")
                    elif period_my_return > period_spy_return:
                        st.info(f"👍 ניצחת את ה-S&P 500 ({period_my_return:+.2f}% vs {period_spy_return:+.2f}%), אך פיגרת אחרי המדד העולמי ({period_vt_return:+.2f}%)")
                    else:
                        diff = period_spy_return - period_my_return
                        st.warning(f"📉 התיק שלך פיגר אחרי ה-S&P 500 ב-{diff:.2f}% בתקופה הנבחרת. שקול לבדוק את ההקצאה.")
                    
                    if failed_tickers:
                        st.caption(f"ℹ️ הגרף לא כולל: {', '.join(failed_tickers)} (אין נתוני היסטוריה)")
                else:
                    st.info("ℹ️ אין נתוני היסטוריה משותפים לגרף, אבל התשואה הכוללת למעלה מחושבת מנתוני הקנייה והמחיר הנוכחי.")
            else:
                st.info("ℹ️ לא ניתן ליצור גרף השוואה, אבל התשואה הכוללת למעלה מחושבת מנתוני הקנייה והמחיר הנוכחי.")
        except Exception as e:
            st.error(f"שגיאה בהשוואה מול השוק: {e}")

    except Exception as e:
        st.error(f"שגיאה במשיכת נתונים: {e}")
        st.info("טיפ: וודא שהטיקרים נכונים ושיש חיבור לאינטרנט.")


# ==================== TAB 2: שיעורים פרטיים ====================
with lessons_tab:
    from lessons_dashboard import render_lessons_dashboard

    render_lessons_dashboard(db, normalize_lesson_record)
