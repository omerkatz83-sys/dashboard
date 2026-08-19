"""Refresh a Supabase market-data snapshot for the Streamlit dashboard.

Run from GitHub Actions or manually:
    python scripts/update_market_snapshot.py

Required environment variables:
    SUPABASE_URL
    SUPABASE_KEY
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_data import fetch_market_quote, quote_has_daily_baseline, utc_now_iso  # noqa: E402


def normalize_rest_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL is missing")
    if url.endswith("/rest/v1"):
        return url
    if "/rest/v1" in url:
        return url.split("/rest/v1", 1)[0] + "/rest/v1"
    return url + "/rest/v1"


def load_literal_assignment(source, name, default):
    module = ast.parse(source.read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    return default


def normalize_ticker(ticker, aliases):
    ticker = str(ticker or "").strip().upper()
    return aliases.get(ticker, ticker)


def supabase_headers(key, prefer=None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def get_state(rest_url, key, row_id, default):
    response = requests.get(
        f"{rest_url}/app_state",
        params={"id": f"eq.{row_id}", "select": "data"},
        headers=supabase_headers(key),
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return default
    return rows[0].get("data", default)


def save_state(rest_url, key, row_id, payload):
    response = requests.post(
        f"{rest_url}/app_state",
        json={"id": row_id, "data": payload},
        headers=supabase_headers(key, "resolution=merge-duplicates,return=representation"),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def collect_tickers(rest_url, key):
    source = ROOT / "dashboard_app.py"
    portfolio = load_literal_assignment(source, "portfolio", {})
    aliases = load_literal_assignment(source, "YAHOO_TICKER_ALIASES", {})

    tickers = {
        normalize_ticker(ticker, aliases)
        for ticker in portfolio
        if str(ticker).upper() not in {"CASH_USD", "CASH_ILS"}
    }

    purchases = get_state(rest_url, key, "purchased_stocks", [])
    if isinstance(purchases, list):
        for purchase in purchases:
            if not isinstance(purchase, dict) or purchase.get("archived_at"):
                continue
            ticker = normalize_ticker(purchase.get("ticker"), aliases)
            if ticker:
                tickers.add(ticker)

    return sorted(tickers)


def main():
    rest_url = normalize_rest_url(os.environ.get("SUPABASE_URL"))
    key = (os.environ.get("SUPABASE_KEY") or "").strip()
    if not key:
        raise RuntimeError("SUPABASE_KEY is missing")

    tickers = collect_tickers(rest_url, key)
    quotes = {}
    errors = {}

    for ticker in tickers:
        try:
            quote, _ = fetch_market_quote(ticker, stock=yf.Ticker(ticker))
            if quote_has_daily_baseline(quote):
                quotes[ticker] = {
                    key: quote.get(key)
                    for key in (
                        "ticker",
                        "price",
                        "previous_close",
                        "change",
                        "change_percent",
                        "currency",
                        "regular_market_time",
                        "source",
                        "updated_at",
                    )
                }
            else:
                errors[ticker] = "missing price or previous_close"
        except Exception as exc:  # keep refreshing the rest of the portfolio
            errors[ticker] = str(exc)

    snapshot = {
        "updated_at": utc_now_iso(),
        "source": "github-actions/yfinance",
        "ticker_count": len(tickers),
        "quote_count": len(quotes),
        "quotes": quotes,
        "errors": errors,
    }
    save_state(rest_url, key, "market_snapshot", snapshot)
    print(json.dumps({k: snapshot[k] for k in ("updated_at", "ticker_count", "quote_count", "errors")}, indent=2))


if __name__ == "__main__":
    main()
