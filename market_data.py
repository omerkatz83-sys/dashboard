"""Shared market-data helpers for the Streamlit app and scheduled refresh job."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


def finite_float(value, default=None):
    """Return a finite float, or default when the source value is missing/invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mapping_get(mapping, key):
    try:
        return mapping.get(key)
    except Exception:
        try:
            return mapping[key]
        except Exception:
            return None


def _series_tail_value(series, offset=-1):
    try:
        if len(series) >= abs(offset):
            return finite_float(series.iloc[offset])
    except Exception:
        return None
    return None


def latest_intraday_frame(stock):
    """Return today's cleaned 5-minute candles, when available."""
    try:
        intraday = stock.history(period="1d", interval="5m")
        if intraday is not None and not intraday.empty:
            clean = intraday.dropna(subset=["Close"])
            if clean is not None and not clean.empty:
                return clean
    except Exception:
        return None
    return None


def fetch_market_quote(ticker, stock=None, history=None):
    """Fetch current price and official previous close for a ticker.

    The important detail is that daily P&L should prefer Yahoo's quote-level
    previous close (`fast_info.previous_close` / `regularMarketPreviousClose`)
    over `history[-2]`. For some LSE ETFs, the daily history can lag or point at
    a different candle than the actual last trading day's quote baseline.
    """
    if stock is None:
        import yfinance as yf

        stock = yf.Ticker(ticker)

    quote = {
        "ticker": ticker,
        "price": None,
        "previous_close": None,
        "currency": None,
        "regular_market_time": None,
        "source": "yfinance",
        "updated_at": utc_now_iso(),
    }

    try:
        fast_info = stock.fast_info
        quote["price"] = finite_float(_mapping_get(fast_info, "last_price"))
        quote["previous_close"] = finite_float(_mapping_get(fast_info, "previous_close"))
        quote["currency"] = _mapping_get(fast_info, "currency")
    except Exception:
        pass

    if quote["price"] is None or quote["previous_close"] is None:
        try:
            info = stock.info or {}
        except Exception:
            info = {}
        if quote["price"] is None:
            quote["price"] = finite_float(
                info.get("regularMarketPrice", info.get("currentPrice"))
            )
        if quote["previous_close"] is None:
            quote["previous_close"] = finite_float(
                info.get("regularMarketPreviousClose", info.get("previousClose"))
            )
        quote["currency"] = quote["currency"] or info.get("currency")
        quote["regular_market_time"] = info.get("regularMarketTime")

    intraday = latest_intraday_frame(stock)
    if quote["price"] is None and intraday is not None:
        quote["price"] = _series_tail_value(intraday["Close"], -1)

    if history is not None:
        if quote["price"] is None:
            quote["price"] = _series_tail_value(history["Close"], -1)
        if quote["previous_close"] is None:
            quote["previous_close"] = _series_tail_value(history["Close"], -2)

    if quote["previous_close"] is not None and quote["previous_close"] <= 0:
        quote["previous_close"] = None
    if quote["price"] is not None and quote["price"] <= 0:
        quote["price"] = None

    if quote["price"] is not None and quote["previous_close"] is not None:
        quote["change"] = quote["price"] - quote["previous_close"]
        quote["change_percent"] = quote["change"] / quote["previous_close"] * 100
    else:
        quote["change"] = None
        quote["change_percent"] = None

    quote["has_intraday"] = intraday is not None
    return quote, intraday


def normalize_snapshot_quotes(snapshot):
    """Return the quotes dict from a stored Supabase market snapshot."""
    if not isinstance(snapshot, dict):
        return {}
    quotes = snapshot.get("quotes")
    return quotes if isinstance(quotes, dict) else {}


def parse_snapshot_time(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def snapshot_quote_is_fresh(quote, max_age_minutes=45):
    """Return True when a stored quote is recent enough to drive Daily P&L."""
    if not quote_has_daily_baseline(quote):
        return False
    updated_at = parse_snapshot_time(quote.get("updated_at"))
    if updated_at is None:
        return False
    return datetime.now(timezone.utc) - updated_at <= timedelta(minutes=max_age_minutes)


def quote_has_daily_baseline(quote):
    if not isinstance(quote, dict):
        return False
    return (
        finite_float(quote.get("price")) is not None
        and finite_float(quote.get("previous_close")) is not None
        and finite_float(quote.get("previous_close")) > 0
    )
