import streamlit as st
st.set_page_config(page_title="Portfolio Command Center 2026", layout="wide")
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import os
import json
import requests
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- עדכון עמלת מסחר ---
TRADE_COMMISSION_USD = 2.00

# --- הגדרת התיק (מחוץ לטאבים - משותף לכולם) ---
# התיק מתחיל ריק לחלוטין
portfolio = {}

# --- מחירי רכישה (Cost Basis) למניה ---
cost_basis = {}

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
        except Exception:
            pass

    # --- Stop Orders ---
    def get_stop_orders(self, default=None):
        return self._load(self._stop_orders_file, default)

    def save_stop_orders(self, data):
        self._save(self._stop_orders_file, data)

    def stop_orders_file_exists(self):
        return os.path.exists(self._stop_orders_file)

    # --- Executed Stops ---
    def get_executed_stops(self):
        return self._load(self._executed_stops_file, [])

    def save_executed_stops(self, data):
        self._save(self._executed_stops_file, data)

    # --- Sold Stocks ---
    def get_sold_stocks(self):
        return self._load(self._sold_stocks_file, [])

    def save_sold_stocks(self, data):
        self._save(self._sold_stocks_file, data)

    # --- Lessons ---
    def get_lessons_data(self, default=None):
        if default is None:
            default = {"lessons": [], "students": []}
        return self._
