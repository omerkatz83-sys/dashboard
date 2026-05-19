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

TRADE_COMMISSION_USD = 4.90

# --- הגדרת התיק (מחוץ לטאבים - משותף לכולם) ---
portfolio = {
    "VUAA.L": {"qty": 190, "type": "Core", "name": "S&P 500"},
    "IEFA": {"qty": 323, "type": "Core", "name": "Developed Mkts ex-US"},
    "IEMG": {"qty": 258, "type": "Core", "name": "Emerging Markets"},
    "AMZN": {"qty": 9, "type": "Satellite", "name": "Amazon"},
    "COIN": {"qty": 9, "type": "Crypto", "name": "Coinbase"},
    "FBTC": {"qty": 57, "type": "Crypto", "name": "Fidelity Bitcoin"},
    "ETH": {"qty": 72, "type": "Crypto", "name": "Grayscale Ethereum Mini Trust"},
    "MSFT": {"qty": 7, "type": "Satellite", "name": "Microsoft"},

    "SFL":  {"qty": 200, "type": "Satellite", "name": "SFL Corporation"},
    "BKR":  {"qty": 35,  "type": "Satellite", "name": "Baker Hughes"},
    "IGV":  {"qty": 30,  "type": "Satellite", "name": "iShares Expanded Tech-Software"},
    "NVDA": {"qty": 16,  "type": "Satellite", "name": "Nvidia"},
    "TSLA": {"qty": 6,   "type": "Satellite", "name": "Tesla"},
    "LIN":  {"qty": 7,   "type": "Satellite", "name": "Linde PLC"},
    "PPA":  {"qty": 15,  "type": "Satellite", "name": "Invesco Aerospace & Defense ETF"},
}

# --- מחירי רכישה (Cost Basis) למניה ---
cost_basis = {
    "VUAA.L":       {"price": 130.81, "currency": "USD", "date": "2025-12-01"},
    "IEFA":         {"price": 88.48,  "currency": "USD", "date": "2025-12-01"},
    "IEMG":         {"price": 67.17,  "currency": "USD", "date": "2025-12-01"},
    "AMZN":         {"price": 243.30, "currency": "USD", "date": "2025-12-01"},
    "COIN":         {"price": 385.60, "currency": "USD", "date": "2025-12-01"},
    "FBTC":         {"price": 88.74,  "currency": "USD", "date": "2026-05-11", "today_buy_qty": 20, "today_buy_price": 71.34},
    "ETH":          {"price": 40.26,  "currency": "USD", "date": "2025-12-01"},
    "MSFT":         {"price": 419.40, "currency": "USD", "date": "2026-04-17"},

    "SFL":          {"price": 11.36,  "currency": "USD", "date": "2026-04-30"},
    "BKR":          {"price": 69.24,  "currency": "USD", "date": "2026-05-04"},
    "IGV":          {"price": 91.03,  "currency": "USD", "date": "2026-05-15"},
    "NVDA":         {"price": 220.00, "currency": "USD", "date": "2026-05-18"},
    "TSLA":         {"price": 434.29, "currency": "USD", "date": "2026-05-12"},
    "LIN":          {"price": 509.00, "currency": "USD", "date": "2026-05-13"},
    "PPA":          {"price": 170.01, "currency": "USD", "date": "2026-05-14"},
    "KSM_SP500":    {"price": 2.3603, "currency": "ILS", "date": "2026-05-19"},
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
        return self._load(self._lessons_file, default)

    def save_lessons_data(self, data):
        self._save(self._lessons_file, data)

    # --- Extra Cash ---
    def get_extra_cash(self):
        return self._load(self._extra_cash_file, {"total_deposited_ils": 0.0, "deposits": []})

    def save_extra_cash(self, data):
        self._save(self._extra_cash_file, data)

    # --- IL Prices ---
    def get_il_prices(self):
        return self._load(self._il_prices_file, {})

    def save_il_prices(self, data):
        self._save(self._il_prices_file, data)

    # --- Baseline ---
    def get_baseline(self):
        return self._load(self._baseline_file, None)

    def save_baseline(self, data):
        self._save(self._baseline_file, data)

    def baseline_exists(self):
        return os.path.exists(self._baseline_file)


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
        except Exception:
            pass

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
        self._set("stop_orders", data)

    def stop_orders_file_exists(self):
        return self._exists("stop_orders")

    # --- Executed Stops ---
    def get_executed_stops(self):
        return self._get("executed_stops", [])

    def save_executed_stops(self, data):
        self._set("executed_stops", data)

    # --- Sold Stocks ---
    def get_sold_stocks(self):
        return self._get("sold_stocks", [])

    def save_sold_stocks(self, data):
        self._set("sold_stocks", data)

    # --- Lessons ---
    def get_lessons_data(self, default=None):
        if default is None:
            default = {"lessons": [], "students": []}
        return self._get("lessons", default)

    def save_lessons_data(self, data):
        self._set("lessons", data)

    # --- Extra Cash ---
    def get_extra_cash(self):
        return self._get("extra_cash", {"total_deposited_ils": 0.0, "deposits": []})

    def save_extra_cash(self, data):
        self._set("extra_cash", data)

    # --- IL Prices ---
    def get_il_prices(self):
        return self._get("il_prices", {})

    def save_il_prices(self, data):
        self._set("il_prices", data)

    # --- Baseline ---
    def get_baseline(self):
        return self._get("baseline", None)

    def save_baseline(self, data):
        self._set("baseline", data)

    def baseline_exists(self):
        return self._exists("baseline")


db = SupabaseDatabase()

# ברירת מחדל — פקודות סטופ פעילות
default_stop_orders = {
    "IEFA":  {"stop_price": 88.50,  "currency": "USD"},
    "IEMG":  {"stop_price": 77.49,  "currency": "USD"},
    "MSFT":  {"stop_price": 414.00, "currency": "USD"},

    "SFL":   {"stop_price": 11.05,  "currency": "USD"},
    "BKR":   {"stop_price": 66.50,  "currency": "USD"},
    "IGV":   {"stop_price": 88.00,  "currency": "USD"},
    "NVDA":  {"stop_price": 212.00, "currency": "USD"},
    "TSLA":  {"stop_price": 418.00, "currency": "USD"},
    "LIN":   {"stop_price": 495.00, "currency": "USD"},
    "PPA":   {"stop_price": 164.50, "currency": "USD"},
}

israeli_stocks = {
    "KSM_SP500": {
        "qty": 9682.00,
        "default_price_ils": 3.433,
        "yf_ticker": None,
        "funder_id": "5122957",  # קסם S&P 500 — משיכת מחיר מ-funder.co.il
        "funder_divisor": 100,    # מחיר funder לחלק ב-100 = מחיר ליחידה
        "type": "Core",
        "name": "S&P 500 (₪)",
        "currency": "ILS"
    },
    "CASH_USD": {
        "qty": -9323.35,
        "default_price_ils": 1.0,
        "yf_ticker": None,
        "type": "Cash",
        "name": "מזומן ($)",
        "currency": "USD"
    },
}


def _normalize_cash_state(raw_state):
    state = raw_state or {}
    state.setdefault("total_deposited_ils", 0.0)
    state.setdefault("deposits", [])
    state.setdefault("sale_cash_usd", 0.0)
    state.setdefault("sale_cash_ils", 0.0)
    return state


def _is_same_sale(existing_sale, sale_entry):
    return (
        existing_sale.get('ticker') == sale_entry.get('ticker')
        and float(existing_sale.get('qty', 0)) == float(sale_entry.get('qty', 0))
        and float(existing_sale.get('sale_price', 0)) == float(sale_entry.get('sale_price', 0))
        and existing_sale.get('date') == sale_entry.get('date')
    )


def _record_sale(db_obj, ticker, name, qty, sale_price, currency, sale_date, stop_price=None, reason='manual'):
    qty = float(qty)
    sale_price = float(sale_price)
    _cb_info = cost_basis.get(ticker, {})
    _cost_per = _cb_info.get('price')
    _commission = TRADE_COMMISSION_USD
    if currency == 'USD':
        _proceeds = round((sale_price * qty) - _commission, 2)
    else:
        _proceeds = round(sale_price * qty, 2)

    sale_entry = {
        'ticker': ticker,
        'name': name,
        'qty': qty,
        'stop_price': stop_price,
        'sale_price': sale_price,
        'proceeds': _proceeds,
        'cost_per_share': _cost_per,
        'commission_usd': _commission,
        'currency': currency,
        'reason': reason,
        'date': sale_date,
    }

    sold_stocks_data = db_obj.get_sold_stocks()
    executed_history = db_obj.get_executed_stops()
    active_stops = db_obj.get_stop_orders(default_stop_orders.copy())
    cash_state = _normalize_cash_state(db_obj.get_extra_cash())

    if not any(_is_same_sale(item, sale_entry) for item in sold_stocks_data):
        sold_stocks_data.append(sale_entry)
    if not any(_is_same_sale(item, sale_entry) for item in executed_history):
        executed_history.append(sale_entry)

    if currency == 'ILS':
        cash_state['sale_cash_ils'] += _proceeds
        cash_state['sale_cash_usd'] -= _commission
    else:
        cash_state['sale_cash_usd'] += _proceeds

    if ticker in active_stops:
        del active_stops[ticker]

    db_obj.save_sold_stocks(sold_stocks_data)
    db_obj.save_executed_stops(executed_history)
    db_obj.save_stop_orders(active_stops)
    db_obj.save_extra_cash(cash_state)
    return sale_entry

# --- טעינת מכירות (סטופים שבוצעו) — הסרת מניות שנמכרו + הוספת תמורה למזומן ---
_sold_stocks = db.get_sold_stocks()
# קבץ לפי טיקר — שמור רק את תאריך המכירה האחרון לכל טיקר
_latest_sale_date = {}
for _sold in _sold_stocks:
    _t = _sold['ticker']
    _sd = _sold.get('date', '')
    if _t not in _latest_sale_date or _sd > _latest_sale_date[_t]:
        _latest_sale_date[_t] = _sd
for _t, _sale_date in _latest_sale_date.items():
    # הסר רק אם תאריך המכירה האחרון הוא אחרי תאריך הרכישה הנוכחי
    _purchase_date_cb = cost_basis.get(_t, {}).get('date', '')
    if _purchase_date_cb and _sale_date[:10] <= _purchase_date_cb:
        continue  # נקנה מחדש אחרי המכירה — לא להסיר
    # הסר מ-portfolio (US stocks)
    if _t in portfolio:
        del portfolio[_t]
    # הסר מ-israeli_stocks
    if _t in israeli_stocks:
        del israeli_stocks[_t]
    # הסר מ-cost_basis
    if _t in cost_basis:
        del cost_basis[_t]

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

def _funder_cache_ttl():
    """מחשב TTL דינמי לפאנדר — רענון פעם ביום, שעתיים אחרי פתיחת מסחר (12:00 IST)"""
    from datetime import timedelta
    import pytz
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    israel_tz = pytz.timezone('Asia/Jerusalem')
    now_il = now_utc.astimezone(israel_tz)
    # מועד הרענון הבא: 12:00 ישראל (שעתיים אחרי פתיחת מסחר)
    refresh_today = now_il.replace(hour=12, minute=0, second=0, microsecond=0)
    if now_il >= refresh_today:
        # כבר עבר 12:00 היום — הרענון הבא מחר ב-12:00
        next_refresh = refresh_today + timedelta(days=1)
    else:
        next_refresh = refresh_today
    ttl_seconds = max(int((next_refresh - now_il).total_seconds()), 60)
    return ttl_seconds

def get_funder_price(fund_id):
    """משיכת מחיר קרן נאמנות מאתר funder.co.il"""
    import re as _re
    try:
        r = requests.get(
            f'https://www.funder.co.il/fund/{fund_id}',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15
        )
        if r.ok:
            m = _re.search(r'"buyPrice":([\d.]+)', r.text)
            if m:
                return float(m.group(1))
    except:
        pass
    return None

def _funder_target_refresh_date():
    """תאריך היעד לעדכון: אחרי 12:00 ישראל - היום, לפני כן - אתמול."""
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
    """משיכת נתוני 52-week high + תאריך אקס-דיבידנד לכל הטיקרים"""
    data = {}
    for ticker in tickers_tuple:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            data[ticker] = {
                '52w_high': info.get('fiftyTwoWeekHigh'),
                '52w_low': info.get('fiftyTwoWeekLow'),
                'ex_div_date': info.get('exDividendDate'),   # unix timestamp
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

            # מחיר נוכחי ו-Low intraday: שלוף נרות 5 דקות — מדויק יותר מנר יומי
            try:
                intraday = stock.history(period="1d", interval="5m")
                if not intraday.empty:
                    intraday_clean = intraday.dropna(subset=['Close'])
                    if not intraday_clean.empty:
                        price = float(intraday_clean['Close'].iloc[-1])
                        # שמור את ה-DataFrame המלא לסינון לפי חותמת זמן בבדיקות סטופ
                        history_dict[f"{ticker}__intraday"] = intraday_clean
                    else:
                        price = float(hist_clean['Close'].iloc[-1])
                else:
                    price = float(hist_clean['Close'].iloc[-1])
            except Exception:
                price = float(hist_clean['Close'].iloc[-1])

            prev_close = float(hist_clean['Close'].iloc[-1]) if len(hist_clean) > 0 else price
            if len(hist_clean) > 1:
                prev_close = float(hist_clean['Close'].iloc[-2])
            
            # אם מניה נקנתה/הוגדלה היום — תקן את Prev Close בהתאם
            cb = cost_basis.get(ticker)
            if cb and cb.get('date'):
                from datetime import date as _date
                try:
                    buy_date = _date.fromisoformat(cb['date'])
                    if buy_date == _date.today():
                        today_buy_qty = cb.get('today_buy_qty')
                        if today_buy_qty and today_buy_qty < info['qty']:
                            # הוספה לפוזיציה קיימת: Prev Close ממוצע משוקלל
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
tab1, tab2, tab3, tab4 = st.tabs(["📊 דשבורד ראשי", "🤖 ניתוח AI מתקדם", "🎯 חזית היעילות", "📚 שיעורים פרטיים"])

# ==================== TAB 1: דשבורד ראשי ====================
with tab1:
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
    _total_deposited_ils = _saved_deposits.get("total_deposited_ils", 0.0)
    _sale_cash_usd = _saved_deposits.get("sale_cash_usd", 0.0)
    _sale_cash_ils = _saved_deposits.get("sale_cash_ils", 0.0)
    
    extra_cash_ils = st.sidebar.number_input(
        "💵 הפקדת מזומן חדשה (₪)",
        min_value=0.0, value=0.0, step=100.0, format="%.0f",
        help="הקלד סכום בשקלים ולחץ 'הפקד' — יומר לדולרים ויתווסף לצמיתות ליתרת המזומן"
    )
    
    if st.sidebar.button("✅ הפקד", disabled=(extra_cash_ils <= 0)):
        _saved_deposits["total_deposited_ils"] = _total_deposited_ils + extra_cash_ils
        _saved_deposits.setdefault("deposits", []).append({
            "amount_ils": extra_cash_ils,
            "date": __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        db.save_extra_cash(_saved_deposits)
        _total_deposited_ils += extra_cash_ils
        st.sidebar.success(f"✅ הופקדו ₪{extra_cash_ils:,.0f} בהצלחה!")
        st.rerun()
    
    # הסכום הנוסף שמתווסף ל-CASH_USD בזמן ריצה
    extra_cash_ils = _total_deposited_ils
    
    if _total_deposited_ils > 0:
        st.sidebar.caption(f"💰 סה״כ הופקד: ₪{_total_deposited_ils:,.0f}")
    
    st.sidebar.caption("מחירי קרנות ישראליות:")
    
    # --- שמירת מחירים לקובץ JSON כדי ששום rerun לא ימחק אותם ---
    saved_prices = db.get_il_prices()
    
    il_prices = {}
    _il_prices_changed = False
    for ticker, info in israeli_stocks.items():
        if info.get('currency') == 'USD' or ticker == 'CASH_USD':
            il_prices[ticker] = info['default_price_ils']
            continue
        
        # --- נכסים עם funder_id — מחיר אוטומטי, בלי input ידני ---
        _funder_id = info.get('funder_id')
        if _funder_id:
            _marker_key = f"__funder_last_update__{ticker}"
            _target_date = _funder_target_refresh_date()
            _needs_refresh = saved_prices.get(_marker_key) != _target_date

            # כפתור רענון ידני — מאפשר לאלץ שליפה מחדש מ-funder
            _col1, _col2 = st.sidebar.columns([3, 1])
            if _col2.button("🔄", key=f"force_refresh_{ticker}", help=f"רענן מחיר {info['name']} מ-funder"):
                _needs_refresh = True
                if _marker_key in saved_prices:
                    del saved_prices[_marker_key]

            # רענון פעם ביום לפי תאריך היעד
            if _needs_refresh:
                _funder_raw = get_funder_price(_funder_id)
                if _funder_raw:
                    _divisor = info.get('funder_divisor', 1)
                    auto_price = _funder_raw / _divisor
                    saved_prices[ticker] = auto_price
                    saved_prices[_marker_key] = _target_date
                    _il_prices_changed = True

            if ticker in saved_prices:
                il_prices[ticker] = saved_prices[ticker]
                _col1.caption(f"💰 {info['name']} ✅ ₪{il_prices[ticker]:.2f}")
            else:
                il_prices[ticker] = info['default_price_ils']
                _col1.caption(f"💰 {info['name']} ⚠️ ₪{il_prices[ticker]:.2f} (לא עודכן)")
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
        db.save_il_prices(saved_prices)

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
            
            # הוספת מזומן נוסף מה-sidebar ומכירות שכבר נרשמו
            if ticker == 'CASH_USD' and extra_cash_ils > 0:
                extra_usd = extra_cash_ils / usd_to_ils
                qty = qty + extra_usd
            if ticker == 'CASH_USD' and _sale_cash_usd != 0:
                qty = qty + _sale_cash_usd
            
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
            _manual_count = sum(1 for _v in israeli_stocks.values() if not _v.get('funder_id') and _v.get('currency') != 'USD' and not _v.get('yf_ticker'))
            if _manual_count > 0:
                st.info(f"ℹ️ {_manual_count} נכסים ישראליים עם מחירים ידניים")

        # Baseline tracking — מבוסס על שווי השקעות בלבד (ללא מזומן) כדי שהוספת מזומן לא תיראה כרווח
        today = datetime.now().strftime('%Y-%m-%d')
        
        if db.baseline_exists():
            baseline_data = db.get_baseline()
            baseline_value = baseline_data.get('invested_value', baseline_data.get('value', total_invested))
            baseline_date = baseline_data.get('date', today)
        else:
            baseline_value = total_invested
            baseline_date = today
            db.save_baseline({'invested_value': total_invested, 'date': baseline_date})
        
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

        # ==================== STOP MARKET ORDERS ====================
        try:
            st.divider()
            st.subheader("🛑 פקודות Stop Market")
            
            # טען פקודות סטופ פעילות וביצועים קודמים
            active_stops = db.get_stop_orders(default_stop_orders.copy())
            executed_history = db.get_executed_stops()
            
            # העבר פורמט ישן (מספר בלבד) לפורמט חדש (dict עם currency)
            for _sk, _sv in list(active_stops.items()):
                if isinstance(_sv, (int, float)):
                    active_stops[_sk] = {"stop_price": _sv, "currency": "USD"}
            
            # סנכרן סטופים חדשים מ-default שלא קיימים ב-DB
            _sync_needed = False
            for _dk, _dv in default_stop_orders.items():
                if _dk not in active_stops:
                    active_stops[_dk] = _dv
                    _sync_needed = True

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
                db.save_stop_orders(active_stops)
            
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
                db.save_stop_orders(active_stops)
            
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
                        'date': datetime.now().strftime('%Y-%m-%d %H:%M')
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
                            sale_date=datetime.now().strftime('%Y-%m-%d %H:%M'),
                            stop_price=ex['stop_price'],
                            reason='stop',
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
                            active_stops[_edit_stop_ticker]['stop_price'] = round(_new_stop_price, 2)
                            # בדיקת Low תסנן רק נרות שנצברו אחרי רגע זה
                            active_stops[_edit_stop_ticker]['check_from_ts'] = datetime.utcnow().isoformat()
                            db.save_stop_orders(active_stops)
                            st.success(f"✅ סטופ {_edit_stop_ticker} עודכן ל-{_stop_sym}{_new_stop_price:,.2f}")
                            st.rerun()
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
                            sale_date=datetime.now().strftime('%Y-%m-%d %H:%M'),
                            stop_price=_manual_stop,
                            reason='manual',
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
                        _is_ils = ex.get('currency') == "ILS"
                        sym = "₪" if _is_ils else "$"
                        _sale_p = ex.get('sale_price', ex.get('market_price', ex['stop_price']))
                        _qty = ex.get('qty', 0)
                        _commission = ex.get('commission_usd', 0.0)
                        _gross_proceeds = _sale_p * _qty
                        _stored_proceeds = ex.get('proceeds')
                        if _stored_proceeds is None:
                            _proceeds = round(_gross_proceeds - (_commission if not _is_ils else 0.0), 2)
                        elif (not _is_ils) and _commission and abs(float(_stored_proceeds) - _gross_proceeds) < 0.02:
                            _proceeds = round(float(_stored_proceeds) - _commission, 2)
                        else:
                            _proceeds = float(_stored_proceeds)
                        # חישוב רווח/הפסד — קודם מהרשומה עצמה, אחרת מה-cost_basis
                        _cost_per = ex.get('cost_per_share')
                        if _cost_per is None:
                            _cb = cost_basis.get(ex['ticker'])
                            _cost_per = _cb['price'] if _cb else None
                        if _cost_per:
                            _total_cost = _cost_per * _qty
                            _pnl = _proceeds - _total_cost
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
        
        # נתוני דיבידנד ברירת מחדל (דיבידנד שנתי למניה $)
        default_dividends = {
            "IEFA":   3.18,   # ~3.27% yield
            "IEMG":   1.85,   # ~2.47% yield
            "NVDA":   0.04,   # ~0.02% yield
            "BKR":    0.92,   # ~1.50% yield
            "PPA":    0.66,   # ~0.37% yield
            "XLE":    2.16,   # ~3.92% yield
            "TXT":    0.08,   # ~0.08% yield
            "BA":     0.00,   # suspended dividend
            "AAPL":   1.00,   # ~0.38% yield
            "TAN":    0.27,   # ~0.48% yield
        }
        
        # כפתור עדכון דיבידנדים מ-API
        div_col1, div_col2 = st.columns([1, 4])
        with div_col1:
            update_div = st.button("🔄 עדכן דיבידנדים", help="משיכת נתוני דיבידנד עדכניים מ-yfinance (לוקח ~30 שניות)")
        
        if update_div:
            with st.spinner("⏳ מושך נתוני דיבידנד עדכניים..."):
                fetch_live_dividends.clear()
                live = fetch_live_dividends(tuple(default_dividends.keys()))
            if live:
                st.session_state['live_dividends'] = live
                with div_col2:
                    st.success(f"✅ עודכנו {len(live)} נכסים!")
            else:
                with div_col2:
                    st.warning("⚠️ לא הצליח לעדכן")
        
        # שימוש בנתונים live אם עודכנו, אחרת defaults
        if 'live_dividends' in st.session_state:
            known_dividends = {**default_dividends, **st.session_state['live_dividends']}
        else:
            known_dividends = default_dividends
        
        div_rows = []
        total_annual_div_usd = 0
        
        for ticker, div_per_share in known_dividends.items():
            if ticker not in portfolio:
                continue
            asset_row = df[df['Ticker'] == ticker]
            if asset_row.empty:
                continue
            
            price = float(asset_row['Price'].iloc[0])
            asset_value = float(asset_row['Value'].iloc[0])
            qty = portfolio[ticker]['qty']
            info = portfolio[ticker]
            
            annual_income = div_per_share * qty
            actual_yield = div_per_share / price * 100 if price > 0 else 0
            
            total_annual_div_usd += annual_income
            
            div_rows.append({
                'שם': info['name'],
                'טיקר': ticker,
                'Yield (%)': actual_yield,
                'דיבידנד שנתי למניה ($)': div_per_share,
                'הכנסה שנתית ($)': annual_income,
                'הכנסה שנתית (₪)': annual_income * usd_to_ils,
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
                    'הכנסה שנתית (₪)': '₪{:,.0f}'
                }),
                width='stretch'
            )
            
            non_div_count = len(portfolio) - len(div_rows)
            if non_div_count > 0:
                st.caption(f"ℹ️ {non_div_count} נכסים בתיק לא מחלקים דיבידנד (VUAA.L, AMZN, COIN, FBTC, ETH).")
            st.caption("💡 סכומי הדיבידנד מבוססים על ברירת מחדל. לחץ '🔄 עדכן דיבידנדים' לקבלת נתונים עדכניים מ-yfinance.")
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
            
            # מזומן (כולל תמורות מכירות ודולרים נוספים שנטענו)
            cash_usd = israeli_stocks.get('CASH_USD', {}).get('qty', 0) + _sale_cash_usd
            if _total_deposited_ils > 0:
                cash_usd += _total_deposited_ils / usd_ils
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



# ==================== TAB 2: ניתוח AI מתקדם ====================
with tab2:
    st.title("🤖 ניתוח AI מקצועי - טכני ופונדמנטלי")
    st.write("ניתוח מעמיק מבוסס בינה מלאכותית עם גרפים אינטראקטיביים וציונים כמותיים")
    
    # בחירת מניה לניתוח
    stock_options = {f"{data['name']} ({ticker})": ticker for ticker, data in portfolio.items()}
    selected_stock_display = st.selectbox("בחר מניה לניתוח מעמיק:", list(stock_options.keys()))
    selected_ticker = stock_options[selected_stock_display]
    
    if st.button("🔄 רענן ניתוח", key="refresh_analysis"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    
    try:
        # טעינת נתוני המניה - נתונים מעודכנים
        stock = yf.Ticker(selected_ticker)
        
        # נתונים טריים ללא cache לניתוח AI
        with st.spinner('טוען נתונים עדכניים מהשוק...'):
            info = stock.info
            hist = stock.history(period="1y")  # שנה מלאה לניתוח מעמיק
            
            # מידע נוסף עדכני
            recommendations = stock.recommendations
            news = stock.news if hasattr(stock, 'news') else []
        
        if hist.empty:
            st.error(f"אין מספיק נתונים היסטוריים עבור {selected_ticker}")
            st.stop()
        
        stock_name = info.get('longName', info.get('shortName', selected_ticker))
        
        # הצגת זמן עדכון
        from datetime import datetime
        update_time = datetime.now().strftime("%H:%M:%S")
        st.info(f"🕐 נתונים עודכנו ב: {update_time} | מקור: Yahoo Finance Real-Time")
        
        # === חלק 1: סיכום כללי וציונים ===
        st.header(f"📈 {stock_name}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("💰 מחיר נוכחי")
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            price_change = ((current_price - prev_price) / prev_price * 100)
            
            # מחיר היום
            today_open = hist['Open'].iloc[-1]
            day_change = ((current_price - today_open) / today_open * 100)
            
            st.metric("מחיר", f"${current_price:.2f}", delta=f"{price_change:+.2f}%")
            st.caption(f"שינוי היום: {day_change:+.2f}%")
        
        with col2:
            st.subheader("📊 ניקוד טכני AI")
            # חישוב ציון טכני משופר (0-100)
            technical_score = 0
            
            # RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]
            
            if 30 < current_rsi < 70:
                technical_score += 30
            elif current_rsi <= 30:
                technical_score += 20  # oversold - potential buy
            else:
                technical_score += 10  # overbought
            
            # Moving Averages - כולל MA150!
            ma_20 = hist['Close'].rolling(window=20).mean()
            ma_50 = hist['Close'].rolling(window=50).mean()
            ma_150 = hist['Close'].rolling(window=150).mean()
            ma_200 = hist['Close'].rolling(window=200).mean()
            
            if current_price > ma_20.iloc[-1]:
                technical_score += 15
            if current_price > ma_50.iloc[-1]:
                technical_score += 15
            if current_price > ma_150.iloc[-1]:
                technical_score += 15
            if current_price > ma_200.iloc[-1]:
                technical_score += 15
            
            # Volume trend
            avg_volume = hist['Volume'].mean()
            recent_volume = hist['Volume'].iloc[-5:].mean()
            if recent_volume > avg_volume * 1.2:
                technical_score += 20
            
            # הצגת ציון עם צבע
            if technical_score >= 75:
                st.success(f"🟢 {technical_score}/100")
            elif technical_score >= 50:
                st.warning(f"🟡 {technical_score}/100")
            else:
                st.error(f"🔴 {technical_score}/100")
        
        with col3:
            st.subheader("🎯 ניקוד פונדמנטלי AI")
            fundamental_score = 0
            
            # P/E Ratio
            pe_ratio = info.get('trailingPE', None)
            if pe_ratio:
                if 10 < pe_ratio < 25:
                    fundamental_score += 25
                elif pe_ratio <= 10:
                    fundamental_score += 15
                else:
                    fundamental_score += 5
            
            # PEG Ratio
            peg = info.get('pegRatio', None)
            if peg and 0 < peg < 1.5:
                fundamental_score += 20
            
            # Profit Margins
            profit_margin = info.get('profitMargins', None)
            if profit_margin and profit_margin > 0.15:
                fundamental_score += 20
            
            # Revenue Growth
            revenue_growth = info.get('revenueGrowth', None)
            if revenue_growth and revenue_growth > 0.1:
                fundamental_score += 20
            
            # Debt to Equity
            debt_to_equity = info.get('debtToEquity', None)
            if debt_to_equity:
                if debt_to_equity < 50:
                    fundamental_score += 15
                elif debt_to_equity < 100:
                    fundamental_score += 10
            
            if fundamental_score >= 75:
                st.success(f"🟢 {fundamental_score}/100")
            elif fundamental_score >= 50:
                st.warning(f"🟡 {fundamental_score}/100")
            else:
                st.error(f"🔴 {fundamental_score}/100")
        
        st.divider()
        
        # === חלק 2: ניתוח טכני מפורט ===
        st.header("📊 ניתוח טכני מתקדם")
        
        # תת-חלוקה לשני עמודות
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("📉 גרף מחירים + אינדיקטורים")
            
            # יצירת גרף מחירים עם Moving Averages מלא
            fig_price = px.line(hist.reset_index(), x='Date', y='Close', 
                               title=f'מחיר {stock_name} + ממוצעים נעים (MA20, MA50, MA150, MA200)')
            
            # הוספת כל הממוצעים
            hist_with_ma = hist.copy()
            hist_with_ma['MA20'] = ma_20
            hist_with_ma['MA50'] = ma_50
            hist_with_ma['MA150'] = ma_150
            hist_with_ma['MA200'] = ma_200
            
            fig_price.add_scatter(x=hist_with_ma.index, y=hist_with_ma['MA20'], 
                                 mode='lines', name='MA20', line=dict(color='orange', width=1.5))
            fig_price.add_scatter(x=hist_with_ma.index, y=hist_with_ma['MA50'], 
                                 mode='lines', name='MA50', line=dict(color='red', width=2))
            fig_price.add_scatter(x=hist_with_ma.index, y=hist_with_ma['MA150'], 
                                 mode='lines', name='MA150', line=dict(color='purple', width=2.5, dash='dash'))
            fig_price.add_scatter(x=hist_with_ma.index, y=hist_with_ma['MA200'], 
                                 mode='lines', name='MA200', line=dict(color='brown', width=3, dash='dot'))
            
            fig_price.update_layout(height=400, showlegend=True)
            st.plotly_chart(fig_price, width='stretch')
            
            st.subheader("📊 נפח מסחר + ממוצע")
            # הוספת קו ממוצע נפח
            fig_volume = px.bar(hist.reset_index(), x='Date', y='Volume',
                               title='נפח מסחר יומי')
            fig_volume.add_hline(y=avg_volume, line_dash="dash", line_color="red", 
                               annotation_text=f"ממוצע: {avg_volume:,.0f}")
            fig_volume.update_layout(height=300)
            st.plotly_chart(fig_volume, width='stretch')
        
        with col_right:
            st.subheader("🎯 אינדיקטורים טכניים")
            
            # RSI
            st.write("**RSI (14) - Relative Strength Index**")
            st.write(f"ערך נוכחי: **{current_rsi:.2f}**")
            
            if current_rsi > 70:
                st.error("🔴 Overbought - המניה קנויה יתר על המידה")
            elif current_rsi < 30:
                st.success("🟢 Oversold - המניה מכורה יתר על המידה (הזדמנות קניה?)")
            else:
                st.info("🟡 טווח נייטרלי")
            
            # גרף RSI
            fig_rsi = px.line(rsi.reset_index(), x='Date', y='Close',
                             title='RSI - 14 ימים')
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought")
            fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold")
            fig_rsi.update_layout(height=250)
            st.plotly_chart(fig_rsi, width='stretch')
            
            # Moving Averages Analysis - מעודכן עם MA150 ו-MA200
            st.write("**Moving Averages - ממוצעים נעים מלאים**")
            ma_20_val = ma_20.iloc[-1]
            ma_50_val = ma_50.iloc[-1]
            ma_150_val = ma_150.iloc[-1]
            ma_200_val = ma_200.iloc[-1]
            
            # טבלת ממוצעים
            ma_data = {
                "ממוצע": ["MA(20)", "MA(50)", "MA(150)", "MA(200)", "מחיר נוכחי"],
                "ערך ($)": [
                    f"${ma_20_val:.2f}", 
                    f"${ma_50_val:.2f}",
                    f"${ma_150_val:.2f}",
                    f"${ma_200_val:.2f}",
                    f"${current_price:.2f}"
                ],
                "מרחק מהמחיר": [
                    f"{((current_price - ma_20_val) / ma_20_val * 100):+.1f}%",
                    f"{((current_price - ma_50_val) / ma_50_val * 100):+.1f}%",
                    f"{((current_price - ma_150_val) / ma_150_val * 100):+.1f}%",
                    f"{((current_price - ma_200_val) / ma_200_val * 100):+.1f}%",
                    "-"
                ]
            }
            st.table(pd.DataFrame(ma_data))
            
            # ניתוח מגמה מתקדם
            above_count = sum([
                current_price > ma_20_val,
                current_price > ma_50_val,
                current_price > ma_150_val,
                current_price > ma_200_val
            ])
            
            if above_count == 4:
                st.success("🟢🟢 מגמת עליה חזקה מאוד - המחיר מעל כל הממוצעים!")
            elif above_count == 3:
                st.success("🟢 מגמת עליה חזקה")
            elif above_count == 2:
                st.info("🟡 מגמה מעורבת - זהירות")
            elif above_count == 1:
                st.warning("🟠 מגמת ירידה")
            else:
                st.error("🔴 מגמת ירידה חזקה - המחיר מתחת לכל הממוצעים")
            
            # Volatility
            st.write("**תנודתיות (Volatility)**")
            returns = hist['Close'].pct_change()
            volatility = returns.std() * np.sqrt(252) * 100  # annualized
            st.metric("תנודתיות שנתית", f"{volatility:.2f}%")
            
            if volatility < 20:
                st.success("🟢 תנודתיות נמוכה - יציבה")
            elif volatility < 40:
                st.info("🟡 תנודתיות בינונית")
            else:
                st.error("🔴 תנודתיות גבוהה - מסוכנת")
        
        st.divider()
        
        # === חלק 3: ניתוח פונדמנטלי מפורט ===
        st.header("💼 ניתוח פונדמנטלי מעמיק")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("📊 מדדי שווי")
            
            if pe_ratio:
                st.metric("P/E Ratio", f"{pe_ratio:.2f}")
                sector_pe = 20  # ממוצע שוק
                if pe_ratio < sector_pe:
                    st.success(f"✅ מתחת לממוצע שוק ({sector_pe})")
                else:
                    st.warning(f"⚠️ מעל ממוצע שוק ({sector_pe})")
            else:
                st.metric("P/E Ratio", "N/A")
            
            forward_pe = info.get('forwardPE', None)
            if forward_pe:
                st.metric("Forward P/E", f"{forward_pe:.2f}")
            
            pb_ratio = info.get('priceToBook', None)
            if pb_ratio:
                st.metric("P/B Ratio", f"{pb_ratio:.2f}")
                if pb_ratio < 3:
                    st.success("✅ שווי סביר")
                else:
                    st.warning("⚠️ שווי גבוה")
            
            if peg:
                st.metric("PEG Ratio", f"{peg:.2f}")
                if peg < 1:
                    st.success("✅ מחיר נמוך יחסית לצמיחה")
                elif peg < 2:
                    st.info("🟡 שווי הוגן")
                else:
                    st.warning("⚠️ יקר יחסית לצמיחה")
        
        with col2:
            st.subheader("💰 רווחיות")
            
            if profit_margin:
                st.metric("שולי רווח", f"{profit_margin*100:.2f}%")
                if profit_margin > 0.20:
                    st.success("✅ רווחיות מצוינת")
                elif profit_margin > 0.10:
                    st.info("🟡 רווחיות טובה")
                else:
                    st.warning("⚠️ רווחיות נמוכה")
            
            roe = info.get('returnOnEquity', None)
            if roe:
                st.metric("ROE", f"{roe*100:.2f}%")
                if roe > 0.15:
                    st.success("✅ תשואה גבוהה על ההון")
                else:
                    st.info("🟡 תשואה סבירה")
            
            operating_margin = info.get('operatingMargins', None)
            if operating_margin:
                st.metric("שולי תפעול", f"{operating_margin*100:.2f}%")
        
        with col3:
            st.subheader("📈 צמיחה")
            
            if revenue_growth:
                st.metric("צמיחת הכנסות", f"{revenue_growth*100:.2f}%")
                if revenue_growth > 0.20:
                    st.success("✅ צמיחה מהירה")
                elif revenue_growth > 0.10:
                    st.info("🟡 צמיחה בריאה")
                else:
                    st.warning("⚠️ צמיחה איטית")
            
            earnings_growth = info.get('earningsGrowth', None)
            if earnings_growth:
                st.metric("צמיחת רווחים", f"{earnings_growth*100:.2f}%")
            
            # Market Cap
            market_cap = info.get('marketCap', None)
            if market_cap:
                market_cap_b = market_cap / 1e9
                st.metric("שווי שוק", f"${market_cap_b:.2f}B")
        
        st.divider()
        
        # === חלק 4: מאזן פיננסי ===
        st.header("💳 בריאות פיננסית")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏦 חוב והון")
            
            if debt_to_equity:
                st.metric("Debt to Equity", f"{debt_to_equity:.2f}")
                
                # ויזואליזציה
                debt_pct = debt_to_equity / (debt_to_equity + 100) * 100
                equity_pct = 100 - debt_pct
                
                fig_debt = px.pie(values=[debt_pct, equity_pct], 
                                 names=['חוב', 'הון עצמי'],
                                 title='מבנה הון',
                                 color_discrete_sequence=['red', 'green'])
                st.plotly_chart(fig_debt, width='stretch')
                
                if debt_to_equity < 50:
                    st.success("✅ רמת חוב נמוכה - בריאה")
                elif debt_to_equity < 100:
                    st.info("🟡 רמת חוב בינונית")
                else:
                    st.error("🔴 רמת חוב גבוהה - סיכון")
            
            current_ratio = info.get('currentRatio', None)
            if current_ratio:
                st.metric("Current Ratio", f"{current_ratio:.2f}")
                if current_ratio > 1.5:
                    st.success("✅ נזילות טובה")
                elif current_ratio > 1:
                    st.info("🟡 נזילות סבירה")
                else:
                    st.warning("⚠️ בעיות נזילות אפשריות")
        
        with col2:
            st.subheader("💵 תזרים מזומנים")
            
            free_cashflow = info.get('freeCashflow', None)
            if free_cashflow:
                fcf_b = free_cashflow / 1e9
                st.metric("Free Cash Flow", f"${fcf_b:.2f}B")
                if free_cashflow > 0:
                    st.success("✅ תזרים מזומנים חיובי")
                else:
                    st.error("🔴 תזרים מזומנים שלילי")
            
            operating_cashflow = info.get('operatingCashflow', None)
            if operating_cashflow:
                ocf_b = operating_cashflow / 1e9
                st.metric("Operating Cash Flow", f"${ocf_b:.2f}B")
            
            # Dividend
            dividend_yield = info.get('dividendYield', None)
            if dividend_yield:
                st.metric("תשואת דיבידנד", f"{dividend_yield*100:.2f}%")
                if dividend_yield > 0.03:
                    st.success("✅ מניית דיבידנד אטרקטיבית")
        
        st.divider()
        
        # === חלק 5: המלצת AI ===
        st.header("🤖 המלצת AI מסכמת")
        
        # חישוב ציון כולל
        total_score = (technical_score + fundamental_score) / 2
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            # ציון כולל גדול
            st.metric("ציון כולל AI", f"{total_score:.0f}/100", 
                     help="ממוצע משוקלל של ניתוח טכני ופונדמנטלי")
            
            # Progress bar
            st.progress(total_score / 100)
            
            # המלצה
            if total_score >= 75:
                st.success("### 🟢 המלצה: קנייה חזקה")
                st.write("המניה מציגה פונדמנטלים חזקים ומגמה טכנית חיובית")
            elif total_score >= 60:
                st.info("### 🟡 המלצה: קנייה / החזקה")
                st.write("המניה מציגה פוטנציאל טוב עם סיכון מתון")
            elif total_score >= 45:
                st.warning("### 🟠 המלצה: החזקה")
                st.write("מומלץ להמשיך להחזיק אך לא להגדיל פוזיציה")
            else:
                st.error("### 🔴 המלצה: שקול מכירה")
                st.write("המניה מציגה סימני חולשה טכניים ו/או פונדמנטליים")
            
            # נקודות חוזק וחולשה
            st.divider()
            
            col_strength, col_weakness = st.columns(2)
            
            with col_strength:
                st.write("**💪 נקודות חוזק:**")
                if technical_score >= 60:
                    st.write("✅ מגמה טכנית חיובית")
                if fundamental_score >= 60:
                    st.write("✅ פונדמנטלים חזקים")
                if current_rsi < 40:
                    st.write("✅ מחיר אטרקטיבי (RSI נמוך)")
                if debt_to_equity and debt_to_equity < 50:
                    st.write("✅ מאזן פיננסי בריא")
                if revenue_growth and revenue_growth > 0.15:
                    st.write("✅ צמיחה מהירה")
                if above_count >= 3:
                    st.write("✅ מחיר מעל רוב הממוצעים")
            
            with col_weakness:
                st.write("**⚠️ נקודות חולשה:**")
                if technical_score < 40:
                    st.write("🔴 מגמה טכנית שלילית")
                if fundamental_score < 40:
                    st.write("🔴 פונדמנטלים חלשים")
                if current_rsi > 70:
                    st.write("🔴 מחיר מנופח (RSI גבוה)")
                if debt_to_equity and debt_to_equity > 100:
                    st.write("🔴 רמת חוב גבוהה")
                if volatility > 40:
                    st.write("🔴 תנודתיות גבוהה")
                if above_count <= 1:
                    st.write("🔴 מחיר מתחת לרוב הממוצעים")
        
        st.divider()
        
        # === חלק 6: תובנות AI בזמן אמת ===
        st.header("🔥 תובנות AI עדכניות")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📰 חדשות אחרונות")
            try:
                if news and len(news) > 0:
                    for i, article in enumerate(news[:5]):
                        with st.container():
                            title = article.get('title', 'No title')
                            link = article.get('link', '#')
                            publisher = article.get('publisher', 'Unknown')
                            st.markdown(f"**{i+1}.** [{title}]({link})")
                            st.caption(f"מקור: {publisher}")
                            st.divider()
                else:
                    st.info("אין חדשות זמינות כרגע")
            except:
                st.info("לא ניתן לטעון חדשות")
        
        with col2:
            st.subheader("🎯 המלצות אנליסטים עדכניות")
            try:
                if recommendations is not None and not recommendations.empty:
                    recent_recs = recommendations.tail(10)
                    rec_summary = recent_recs['To Grade'].value_counts()
                    
                    # גרף המלצות
                    fig_recs = px.pie(values=rec_summary.values, 
                                     names=rec_summary.index,
                                     title='התפלגות המלצות (10 אחרונות)')
                    st.plotly_chart(fig_recs, width='stretch')
                    
                    # טבלת המלצות אחרונות
                    st.write("**המלצות אחרונות:**")
                    rec_display = recent_recs[['Firm', 'To Grade', 'Action']].tail(5)
                    st.dataframe(rec_display, width=400)
                else:
                    st.info("אין המלצות אנליסטים זמינות")
            except:
                st.info("לא ניתן לטעון המלצות אנליסטים")
        
        st.divider()
        
        # === חלק 7: ביצועים היסטוריים ===
        st.header("📈 ביצועים היסטוריים")
        
        col1, col2, col3, col4 = st.columns(4)
        
        # חישוב תשואות לפי תקופות
        periods = {
            '1 שבוע': 5,
            '1 חודש': 21,
            '3 חודשים': 63,
            '6 חודשים': 126,
            '1 שנה': 252
        }
        
        returns_data = []
        for period_name, days in periods.items():
            if len(hist) > days:
                period_return = ((current_price - hist['Close'].iloc[-days]) / hist['Close'].iloc[-days] * 100)
                returns_data.append({'תקופה': period_name, 'תשואה': f"{period_return:+.2f}%"})
        
        if returns_data:
            col1.write("**תשואות לפי תקופות:**")
            col1.table(pd.DataFrame(returns_data))
        
        # סטטיסטיקות נוספות
        col2.write("**סטטיסטיקות שנתיות:**")
        annual_return = ((hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0] * 100)
        max_price = hist['Close'].max()
        min_price = hist['Close'].min()
        
        col2.metric("תשואה שנתית", f"{annual_return:+.2f}%")
        col2.metric("מקסימום", f"${max_price:.2f}")
        col2.metric("מינימום", f"${min_price:.2f}")
        
        # Sharpe Ratio (פשוט)
        col3.write("**מדדי סיכון:**")
        daily_returns = hist['Close'].pct_change()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
        
        col3.metric("Sharpe Ratio", f"{sharpe:.2f}")
        col3.caption("גבוה = תשואה טובה יחסית לסיכון")
        
        # Max Drawdown
        rolling_max = hist['Close'].cummax()
        drawdown = (hist['Close'] - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()
        
        col3.metric("Max Drawdown", f"{max_drawdown:.2f}%")
        col3.caption("הירידה המקסימלית מהשיא")
        
        # גרף התשואות המצטברות
        col4.write("**צמיחת $1000:**")
        cumulative = (1 + hist['Close'].pct_change()).cumprod() * 1000
        col4.metric("ערך היום", f"${cumulative.iloc[-1]:.2f}")
        col4.caption(f"השקעה ראשונית: $1000")
        
        st.divider()
        
        # === חלק 8: נתונים נוספים ===
        with st.expander("📋 נתונים פיננסיים מפורטים"):
            data_dict = {
                "מדד": ["סקטור", "תעשייה", "מדינה", "מטבע", "עובדים", "אתר"],
                "ערך": [
                    info.get('sector', 'N/A'),
                    info.get('industry', 'N/A'),
                    info.get('country', 'N/A'),
                    info.get('currency', 'N/A'),
                    info.get('fullTimeEmployees', 'N/A'),
                    info.get('website', 'N/A')
                ]
            }
            st.table(pd.DataFrame(data_dict))
        
        with st.expander("📊 היסטוריית מחירים (טבלה - 30 ימים אחרונים)"):
            hist_display = hist[['Open', 'High', 'Low', 'Close', 'Volume']].tail(30)
            st.dataframe(hist_display.style.format({
                'Open': '${:.2f}',
                'High': '${:.2f}',
                'Low': '${:.2f}',
                'Close': '${:.2f}',
                'Volume': '{:,.0f}'
            }), width=800)
    
    except Exception as e:
        st.error(f"שגיאה בניתוח המניה: {str(e)}")
        st.info("אנא בחר מניה אחרת או נסה שוב מאוחר יותר")
    
    st.divider()
    st.caption("🤖 ניתוח זה נוצר באמצעות אלגוריתמים כמותיים ומתעדכן בזמן אמת. אינו מהווה ייעוץ השקעות - המידע לצרכי מידע בלבד.")


# ==================== TAB 3: חזית היעילות (Efficient Frontier) ====================
with tab3:
    st.title("🎯 חזית היעילות (Efficient Frontier)")
    st.markdown("""
    **מודל מרקוביץ (Markowitz Mean-Variance)** — הגביע הקדוש של ניהול תיקים.  
    
    💡 **הרעיון:** המניות שלך נשארות **בדיוק אותן מניות**. מה שמשתנה הוא רק ה**משקלות** (האחוזים) של כל נכס בתיק.  
    כמו בסגסוגת מתכות — החומרים קבועים, אבל שבר המסה של כל רכיב משנה דרמטית את התכונות הסופיות.
    
    הסיכון של תיק **לא** נקבע רק מממוצע משוקלל — אלא מהשונות המשותפת (Covariance) בין הנכסים:
    
    $$\\sigma_p^2 = \\sum_{i} \\sum_{j} w_i \\cdot w_j \\cdot \\sigma_{ij}$$
    
    בגלל המכפלות האלו, שינוי קטן באחוזים יכול **להקטין משמעותית** את הסיכון בלי לפגוע בתשואה.
    """)
    
    st.divider()
    
    # הגדרות סימולציה
    col_settings1, col_settings2, col_settings3 = st.columns(3)
    with col_settings1:
        num_portfolios = st.selectbox("מספר תיקים לסימולציה:", [1000, 3000, 5000, 10000], index=2)
    with col_settings2:
        ef_period = st.selectbox("תקופת נתונים:", ["6mo", "1y", "2y", "3y", "5y"], index=1,
                                  format_func=lambda x: {"6mo": "6 חודשים", "1y": "שנה", "2y": "שנתיים", "3y": "3 שנים", "5y": "5 שנים"}[x])
    with col_settings3:
        risk_free_rate = st.number_input("ריבית חסרת סיכון (%)", min_value=0.0, max_value=10.0, value=4.5, step=0.5) / 100
    
    if st.button("🚀 הרץ סימולציה", key="run_ef"):
        import plotly.graph_objects as go
        from scipy.optimize import minimize
        
        # --- שלב 1: משיכת נתונים היסטוריים ---
        with st.spinner("⏳ שולף נתוני מחירים היסטוריים..."):
            ef_tickers = [t for t in portfolio.keys()]
            raw_prices = {}
            skipped = []
            
            for ticker in ef_tickers:
                try:
                    hist = yf.Ticker(ticker).history(period=ef_period)
                    if not hist.empty and len(hist) > 20:
                        raw_prices[ticker] = hist['Close']
                    else:
                        skipped.append(ticker)
                except:
                    skipped.append(ticker)
            
            if skipped:
                st.warning(f"⚠️ דילגנו על: {', '.join(skipped)} (אין מספיק נתונים)")
        
        if len(raw_prices) < 2:
            st.error("❌ צריך לפחות 2 נכסים עם נתונים כדי להריץ סימולציה.")
            st.stop()
        
        # יישור תאריכים — כל נכס נסחר בימים שונים (לונדון vs ארה"ב vs קריפטו)
        # 1) מאחדים לטבלה אחת לפי union של כל התאריכים
        price_data = pd.DataFrame(raw_prices)
        # 2) מילוי קדימה (Forward Fill) — אם נכס לא נסחר ביום מסוים, לוקחים את המחיר האחרון
        price_data = price_data.ffill()
        # 3) הסרת שורות ראשונות שבהן יש NaN (לפני שהנכס התחיל להיסחר)
        price_data = price_data.dropna(axis=0, how='any')
        
        # 4) הסרת נכסים עם פחות מ-80% מהימים (אם נכס חדש מדי)
        min_coverage = int(len(price_data) * 0.5)
        thin_tickers = [c for c in price_data.columns if price_data[c].count() < min_coverage]
        if thin_tickers:
            st.warning(f"⚠️ הוסרו בגלל כיסוי נמוך: {', '.join(thin_tickers)}")
            price_data = price_data.drop(columns=thin_tickers)
        
        if price_data.shape[1] < 2 or len(price_data) < 30:
            st.error("❌ לא נותרו מספיק נכסים/ימים לסימולציה.")
            st.stop()
        
        ef_tickers_valid = list(price_data.columns)
        n_assets = len(ef_tickers_valid)
        
        st.success(f"✅ {n_assets} נכסים | {len(price_data)} ימי מסחר | תקופה: {ef_period}")
        
        # --- שלב 2: חישוב תשואות יומיות, ממוצע ומטריצת שונות ---
        daily_returns = price_data.pct_change().dropna()
        mean_returns = daily_returns.mean().values * 252     # תשואה שנתית (וקטור)
        cov_matrix = daily_returns.cov().values * 252         # מטריצת שונות שנתית (מערך numpy)
        
        # --- שלב 3: חישוב מיקום התיק הנוכחי ---
        current_values = {}
        for ticker in ef_tickers_valid:
            last_price = float(price_data[ticker].iloc[-1])
            current_values[ticker] = last_price * portfolio[ticker]['qty']
        
        total_ef_value = sum(current_values.values())
        current_weights = np.array([current_values[t] / total_ef_value for t in ef_tickers_valid])
        
        my_return = float(np.dot(current_weights, mean_returns)) * 100
        my_risk = float(np.sqrt(current_weights @ cov_matrix @ current_weights)) * 100
        my_sharpe = (my_return / 100 - risk_free_rate) / (my_risk / 100) if my_risk > 0 else 0
        
        # --- שלב 4: סימולציית מונטה קרלו ---
        with st.spinner(f"⏳ מריץ {num_portfolios:,} הרכבי תיק אקראיים..."):
            results = np.zeros((num_portfolios, 3))  # return, risk, sharpe
            all_weights = np.zeros((num_portfolios, n_assets))
            
            for i in range(num_portfolios):
                w = np.random.dirichlet(np.ones(n_assets))
                all_weights[i] = w
                
                ret = float(np.dot(w, mean_returns))
                risk = float(np.sqrt(w @ cov_matrix @ w))
                
                results[i, 0] = ret * 100
                results[i, 1] = risk * 100
                results[i, 2] = (ret - risk_free_rate) / risk if risk > 0 else 0
        
        # --- שלב 5: אופטימיזציה אנליטית — חזית יעילות אמיתית ---
        with st.spinner("📐 מחשב חזית יעילות אנליטית (Scipy Optimization)..."):
            
            def neg_sharpe(w):
                ret = np.dot(w, mean_returns)
                risk = np.sqrt(w @ cov_matrix @ w)
                return -(ret - risk_free_rate) / risk if risk > 0 else 0
            
            def portfolio_risk(w):
                return np.sqrt(w @ cov_matrix @ w)
            
            def portfolio_return(w):
                return np.dot(w, mean_returns)
            
            bounds = tuple((0, 1) for _ in range(n_assets))
            constraints_sum = {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
            w0 = np.ones(n_assets) / n_assets
            
            # 1) תיק Sharpe מקסימלי (Tangency Portfolio)
            opt_sharpe = minimize(neg_sharpe, w0, method='SLSQP', bounds=bounds, constraints=constraints_sum)
            opt_sharpe_w = opt_sharpe.x
            opt_sharpe_ret = float(np.dot(opt_sharpe_w, mean_returns)) * 100
            opt_sharpe_risk = float(np.sqrt(opt_sharpe_w @ cov_matrix @ opt_sharpe_w)) * 100
            opt_sharpe_val = (opt_sharpe_ret / 100 - risk_free_rate) / (opt_sharpe_risk / 100) if opt_sharpe_risk > 0 else 0
            
            # 2) תיק סיכון מינימלי (Global Minimum Variance)
            opt_minrisk = minimize(portfolio_risk, w0, method='SLSQP', bounds=bounds, constraints=constraints_sum)
            opt_minrisk_w = opt_minrisk.x
            opt_minrisk_ret = float(np.dot(opt_minrisk_w, mean_returns)) * 100
            opt_minrisk_risk = float(np.sqrt(opt_minrisk_w @ cov_matrix @ opt_minrisk_w)) * 100
            
            # 3) חזית יעילות — מייצרים ~50 נקודות לאורך הקו העליון
            target_returns = np.linspace(opt_minrisk_ret / 100, mean_returns.max() * 0.98, 50)
            frontier_risks = []
            frontier_returns = []
            
            for target_ret in target_returns:
                cons = [
                    constraints_sum,
                    {'type': 'eq', 'fun': lambda w, r=target_ret: portfolio_return(w) - r}
                ]
                result = minimize(portfolio_risk, w0, method='SLSQP', bounds=bounds, constraints=cons)
                if result.success:
                    frontier_risks.append(float(np.sqrt(result.x @ cov_matrix @ result.x)) * 100)
                    frontier_returns.append(target_ret * 100)
            
            # 4) תיק "אותו סיכון כמו שלי" — מה התשואה המקסימלית שאפשר?
            cons_same_risk = [
                constraints_sum,
                {'type': 'ineq', 'fun': lambda w: (my_risk / 100) - portfolio_risk(w)}  # risk <= my_risk
            ]
            
            def neg_return(w):
                return -np.dot(w, mean_returns)
            
            opt_same_risk = minimize(neg_return, w0, method='SLSQP', bounds=bounds, constraints=cons_same_risk)
            if opt_same_risk.success:
                same_risk_ret = float(np.dot(opt_same_risk.x, mean_returns)) * 100
                same_risk_risk = float(np.sqrt(opt_same_risk.x @ cov_matrix @ opt_same_risk.x)) * 100
                same_risk_w = opt_same_risk.x
                gap_return = same_risk_ret - my_return
            else:
                same_risk_ret = my_return
                same_risk_risk = my_risk
                same_risk_w = current_weights
                gap_return = 0
            
            # 5) תיק "אותה תשואה כמו שלי" — מה הסיכון המינימלי שאפשר?
            cons_same_ret = [
                constraints_sum,
                {'type': 'eq', 'fun': lambda w: portfolio_return(w) - my_return / 100}
            ]
            opt_same_ret = minimize(portfolio_risk, w0, method='SLSQP', bounds=bounds, constraints=cons_same_ret)
            if opt_same_ret.success:
                same_ret_risk = float(np.sqrt(opt_same_ret.x @ cov_matrix @ opt_same_ret.x)) * 100
                same_ret_ret = float(np.dot(opt_same_ret.x, mean_returns)) * 100
                gap_risk = my_risk - same_ret_risk
            else:
                same_ret_risk = my_risk
                same_ret_ret = my_return
                gap_risk = 0
        
        # --- שלב 6: הצגת KPIs ---
        st.subheader("📊 תוצאות הסימולציה")
        
        kcol1, kcol2, kcol3, kcol4 = st.columns(4)
        kcol1.metric("⭐ תשואה צפויה שלי", f"{my_return:.2f}%")
        kcol2.metric("⭐ סיכון (σ) שלי", f"{my_risk:.2f}%")
        kcol3.metric("⭐ Sharpe שלי", f"{my_sharpe:.2f}")
        kcol4.metric("🏆 Sharpe אופטימלי", f"{opt_sharpe_val:.2f}",
                     delta=f"{my_sharpe - opt_sharpe_val:+.2f}" if opt_sharpe_val > 0 else None)
        
        # KPIs של הפערים
        gcol1, gcol2 = st.columns(2)
        gcol1.metric("📈 תשואה שאתה מפסיד (על אותו סיכון)", 
                     f"{gap_return:+.2f}%",
                     help=f"בסיכון של {my_risk:.1f}%, החזית מאפשרת תשואה של {same_risk_ret:.2f}% במקום {my_return:.2f}%")
        gcol2.metric("🛡️ סיכון מיותר שאתה לוקח (על אותה תשואה)",
                     f"{gap_risk:+.2f}%", 
                     help=f"לתשואה של {my_return:.1f}%, אפשר להגיע עם σ={same_ret_risk:.2f}% במקום {my_risk:.2f}%")
        
        st.divider()
        
        # --- שלב 7: גרף חזית היעילות ---
        st.subheader("🗺️ מפת סיכון-תשואה (Efficient Frontier)")
        
        fig_ef = go.Figure()
        
        # ענן הנקודות — כל הסימולציות
        fig_ef.add_trace(go.Scatter(
            x=results[:, 1], y=results[:, 0],
            mode='markers',
            marker=dict(
                size=3.5,
                color=results[:, 2],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title='Sharpe<br>Ratio', len=0.6),
                opacity=0.5
            ),
            name='תיקים אקראיים',
            hovertemplate='σ: %{x:.2f}%<br>תשואה: %{y:.2f}%<extra></extra>'
        ))
        
        # קו חזית היעילות האמיתי (Scipy)
        if len(frontier_risks) > 2:
            fig_ef.add_trace(go.Scatter(
                x=frontier_risks, y=frontier_returns,
                mode='lines',
                line=dict(color='#FF6B6B', width=3.5),
                name='חזית היעילות (Efficient Frontier)',
                hovertemplate='σ: %{x:.2f}%<br>תשואה: %{y:.2f}%<extra></extra>'
            ))
        
        # נקודת התיק שלי
        fig_ef.add_trace(go.Scatter(
            x=[my_risk], y=[my_return],
            mode='markers+text',
            marker=dict(size=22, color='gold', symbol='star', line=dict(width=2, color='black')),
            text=['⭐ אתה כאן'],
            textposition='top center',
            textfont=dict(size=14, color='gold', family='Arial Black'),
            name='⭐ התיק שלי',
            hovertemplate=f'⭐ התיק שלי<br>σ: {my_risk:.2f}%<br>תשואה: {my_return:.2f}%<br>Sharpe: {my_sharpe:.2f}<extra></extra>'
        ))
        
        # חץ אנכי — פער תשואה (אותו סיכון)
        if gap_return > 0.5:
            fig_ef.add_trace(go.Scatter(
                x=[same_risk_risk], y=[same_risk_ret],
                mode='markers+text',
                marker=dict(size=14, color='#00FF88', symbol='triangle-up', line=dict(width=2, color='black')),
                text=[f'+{gap_return:.1f}%'],
                textposition='top center',
                textfont=dict(size=12, color='#00FF88'),
                name='🎯 אותו סיכון, תשואה טובה יותר',
                hovertemplate=f'על אותו סיכון ({my_risk:.1f}%):<br>תשואה: {same_risk_ret:.2f}% (vs {my_return:.2f}%)<extra></extra>'
            ))
            # קו מקווקו אנכי מהנקודה שלי לחזית
            fig_ef.add_shape(type='line',
                x0=my_risk, y0=my_return, x1=same_risk_risk, y1=same_risk_ret,
                line=dict(color='#00FF88', width=2, dash='dash'))
        
        # חץ אופקי — פער סיכון (אותה תשואה)
        if gap_risk > 0.5:
            fig_ef.add_trace(go.Scatter(
                x=[same_ret_risk], y=[same_ret_ret],
                mode='markers+text',
                marker=dict(size=14, color='#FF9F1C', symbol='triangle-left', line=dict(width=2, color='black')),
                text=[f'-{gap_risk:.1f}%σ'],
                textposition='middle left',
                textfont=dict(size=12, color='#FF9F1C'),
                name='🛡️ אותה תשואה, פחות סיכון',
                hovertemplate=f'על אותה תשואה ({my_return:.1f}%):<br>σ: {same_ret_risk:.2f}% (vs {my_risk:.2f}%)<extra></extra>'
            ))
            fig_ef.add_shape(type='line',
                x0=my_risk, y0=my_return, x1=same_ret_risk, y1=same_ret_ret,
                line=dict(color='#FF9F1C', width=2, dash='dash'))
        
        # תיק Sharpe מקסימלי (אופטימיזציה)
        fig_ef.add_trace(go.Scatter(
            x=[opt_sharpe_risk], y=[opt_sharpe_ret],
            mode='markers+text',
            marker=dict(size=18, color='lime', symbol='diamond', line=dict(width=2, color='black')),
            text=['💎 Tangency'],
            textposition='bottom right',
            textfont=dict(size=11, color='lime'),
            name='💎 Sharpe מקסימלי',
            hovertemplate=f'💎 Tangency Portfolio<br>σ: {opt_sharpe_risk:.2f}%<br>תשואה: {opt_sharpe_ret:.2f}%<br>Sharpe: {opt_sharpe_val:.2f}<extra></extra>'
        ))
        
        # תיק סיכון מינימלי (אופטימיזציה)
        fig_ef.add_trace(go.Scatter(
            x=[opt_minrisk_risk], y=[opt_minrisk_ret],
            mode='markers+text',
            marker=dict(size=16, color='cyan', symbol='square', line=dict(width=2, color='black')),
            text=['🛡️ GMV'],
            textposition='bottom left',
            textfont=dict(size=11, color='cyan'),
            name='🛡️ סיכון מינימלי (GMV)',
            hovertemplate=f'🛡️ Global Min Variance<br>σ: {opt_minrisk_risk:.2f}%<br>תשואה: {opt_minrisk_ret:.2f}%<extra></extra>'
        ))
        
        # Capital Market Line (CML) — קו מריבית חסרת סיכון דרך Tangency
        if opt_sharpe_risk > 0:
            cml_x = np.linspace(0, results[:, 1].max() * 1.05, 100)
            cml_y = risk_free_rate * 100 + opt_sharpe_val * cml_x
            fig_ef.add_trace(go.Scatter(
                x=cml_x, y=cml_y,
                mode='lines',
                line=dict(color='rgba(255,255,255,0.4)', width=1.5, dash='dot'),
                name='CML (Capital Market Line)',
                hoverinfo='skip'
            ))
        
        fig_ef.update_layout(
            title=dict(text=f'חזית היעילות — {num_portfolios:,} תיקים | תקופה: {ef_period}', font=dict(size=20)),
            xaxis_title='סיכון — סטיית תקן שנתית σ (%)',
            yaxis_title='תשואה שנתית צפויה E[R] (%)',
            height=700,
            template='plotly_dark',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
            hovermode="closest"
        )
        
        st.plotly_chart(fig_ef, width='stretch')
        
        # --- הסבר הגרף ---
        with st.expander("🧠 איך לקרוא את הגרף?", expanded=False):
            st.markdown("""
            - **ענן הנקודות**: כל נקודה = הרכב תיק אקראי (אותן מניות, אחוזים שונים). הצבע = Sharpe Ratio.
            - **הקו האדום (חזית היעילות)**: הקו העליון-שמאלי = "חזית פארטו" — תיקים אופטימליים. 
              *אי אפשר לקבל יותר תשואה בלי לקחת יותר סיכון.*
            - **⭐ הנקודה שלך**: אם היא **מתחת לקו האדום** — אתה לוקח סיכון מיותר.
            - **חץ ירוק ↑**: כמה תשואה אתה מפסיד — על אותו סיכון, החזית מאפשרת יותר.
            - **חץ כתום ←**: כמה סיכון מיותר — על אותה תשואה, אפשר עם פחות.
            - **💎 Tangency**: התיק עם Sharpe הגבוה ביותר (יחס תשואה-לסיכון מיטבי).
            - **🛡️ GMV**: Global Minimum Variance — הסיכון הנמוך ביותר האפשרי.
            - **קו מקווקו (CML)**: Capital Market Line — שילוב אופטימלי של נכס חסר-סיכון + Tangency.
            """)
        
        st.divider()
        
        # --- שלב 8: מטריצת מתאמים ---
        st.subheader("🔗 מטריצת מתאמים (Correlation Matrix)")
        st.caption("ככל שהמתאם בין שני נכסים **נמוך יותר**, ה**דיברסיפיקציה** ביניהם טובה יותר — זה מה שמקטין את σ של התיק.")
        
        corr_matrix = daily_returns.corr()
        
        # שם קריא
        corr_labels = [portfolio[t]['name'] if t in portfolio else t for t in ef_tickers_valid]
        
        fig_corr = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_labels, y=corr_labels,
            colorscale='RdBu_r',
            zmin=-1, zmax=1,
            text=np.round(corr_matrix.values, 2),
            texttemplate='%{text}',
            textfont=dict(size=10),
            colorbar=dict(title='ρ')
        ))
        fig_corr.update_layout(
            title='מתאם בין הנכסים (Pearson Correlation)',
            height=500,
            template='plotly_dark'
        )
        st.plotly_chart(fig_corr, width='stretch')
        
        # מתאמים בולטים
        low_corrs = []
        high_corrs = []
        for i in range(n_assets):
            for j in range(i + 1, n_assets):
                rho = corr_matrix.values[i, j]
                pair = f"{corr_labels[i]} ↔ {corr_labels[j]}"
                if rho < 0.3:
                    low_corrs.append((pair, rho))
                elif rho > 0.8:
                    high_corrs.append((pair, rho))
        
        if low_corrs or high_corrs:
            ccol1, ccol2 = st.columns(2)
            with ccol1:
                st.write("**✅ מתאם נמוך (גיוון טוב):**")
                for pair, rho in sorted(low_corrs, key=lambda x: x[1]):
                    st.write(f"• {pair}: **ρ = {rho:.2f}**")
                if not low_corrs:
                    st.write("לא נמצאו זוגות עם מתאם נמוך.")
            with ccol2:
                st.write("**⚠️ מתאם גבוה (חשיפה כפולה):**")
                for pair, rho in sorted(high_corrs, key=lambda x: -x[1]):
                    st.write(f"• {pair}: **ρ = {rho:.2f}**")
                if not high_corrs:
                    st.write("אין זוגות עם מתאם גבוה מדי — מצוין!")
        
        st.divider()
        
        # --- שלב 9: טבלת השוואה ---
        st.subheader("📋 השוואת תיקים — שלך מול האופטימום")
        
        compare_data = {
            "": ["⭐ התיק שלי", "💎 Tangency (Sharpe מקסימלי)", "🛡️ GMV (סיכון מינימלי)", "🎯 חזית — אותו σ", "🎯 חזית — אותו E[R]"],
            "תשואה E[R]": [f"{my_return:.2f}%", f"{opt_sharpe_ret:.2f}%", f"{opt_minrisk_ret:.2f}%", f"{same_risk_ret:.2f}%", f"{same_ret_ret:.2f}%"],
            "סיכון σ": [f"{my_risk:.2f}%", f"{opt_sharpe_risk:.2f}%", f"{opt_minrisk_risk:.2f}%", f"{same_risk_risk:.2f}%", f"{same_ret_risk:.2f}%"],
            "Sharpe": [f"{my_sharpe:.2f}", f"{opt_sharpe_val:.2f}", f"{(opt_minrisk_ret/100 - risk_free_rate)/(opt_minrisk_risk/100):.2f}" if opt_minrisk_risk > 0 else "N/A", "—", "—"]
        }
        st.table(pd.DataFrame(compare_data))
        
        # --- שלב 10: הרכב תיקים אופטימליים ---
        st.subheader("💎 השוואת הרכבים — משקלות כל נכס")
        
        weights_rows = []
        for i, ticker in enumerate(ef_tickers_valid):
            name = portfolio[ticker]['name'] if ticker in portfolio else ticker
            weights_rows.append({
                'טיקר': ticker,
                'שם': name,
                'סוג': portfolio[ticker]['type'],
                'שלי (%)': current_weights[i] * 100,
                'Tangency (%)': opt_sharpe_w[i] * 100,
                'GMV (%)': opt_minrisk_w[i] * 100,
                'חזית-אותו σ (%)': same_risk_w[i] * 100,
                'הפרש מ-Tangency': (opt_sharpe_w[i] - current_weights[i]) * 100
            })
        
        weights_df = pd.DataFrame(weights_rows).sort_values('Tangency (%)', ascending=False)
        
        # צביעת עמודת הפרש ידנית (בלי background_gradient)
        def color_diff(val):
            if isinstance(val, (int, float)):
                if val > 5:
                    return 'background-color: #1a472a; color: #4ade80'
                elif val > 0:
                    return 'background-color: #14331f; color: #86efac'
                elif val < -5:
                    return 'background-color: #4a1a1a; color: #f87171'
                elif val < 0:
                    return 'background-color: #331414; color: #fca5a5'
            return ''
        
        st.dataframe(
            weights_df.style.format({
                'שלי (%)': '{:.1f}%',
                'Tangency (%)': '{:.1f}%',
                'GMV (%)': '{:.1f}%',
                'חזית-אותו σ (%)': '{:.1f}%',
                'הפרש מ-Tangency': '{:+.1f}%'
            }).map(color_diff, subset=['הפרש מ-Tangency']),
            width='stretch'
        )
        
        # --- שלב 11: גרף עוגה — שלי vs אופטימלי ---
        st.subheader("🥧 השוואת הקצאות")
        
        pie_col1, pie_col2 = st.columns(2)
        with pie_col1:
            fig_pie_mine = px.pie(
                values=current_weights * 100,
                names=[portfolio[t]['name'] for t in ef_tickers_valid],
                title='⭐ התיק שלי — הקצאה נוכחית',
                hole=0.35
            )
            fig_pie_mine.update_layout(height=400, template='plotly_dark', showlegend=True)
            st.plotly_chart(fig_pie_mine, width='stretch')
        
        with pie_col2:
            fig_pie_opt = px.pie(
                values=opt_sharpe_w * 100,
                names=[portfolio[t]['name'] for t in ef_tickers_valid],
                title='💎 Tangency — הקצאה אופטימלית',
                hole=0.35
            )
            fig_pie_opt.update_layout(height=400, template='plotly_dark', showlegend=True)
            st.plotly_chart(fig_pie_opt, width='stretch')
        
        st.divider()
        
        # --- שלב 12: ניתוח AI מסכם ---
        st.subheader("🤖 ניתוח AI מסכם — מסקנות והמלצות")
        
        # --- איסוף כל הנתונים לניתוח ---
        # 1) ניתוח יעילות התיק
        efficiency_score = min(my_sharpe / opt_sharpe_val * 100, 100) if opt_sharpe_val > 0 else 0
        
        # 2) ניתוח דיברסיפיקציה
        avg_corr = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].mean()
        max_corr_val = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].max()
        min_corr_val = corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].min()
        
        # 3) ריכוזיות
        hhi = np.sum(current_weights ** 2) * 10000  # Herfindahl-Hirschman Index
        top3_weight = np.sort(current_weights)[-3:].sum() * 100
        
        # 4) חשיפה לפי סוג
        type_weights = {}
        for i, ticker in enumerate(ef_tickers_valid):
            t = portfolio[ticker]['type']
            type_weights[t] = type_weights.get(t, 0) + current_weights[i] * 100
        
        # 5) ביצועי נכסים בודדים
        individual_returns = mean_returns * 100
        individual_risks = np.sqrt(np.diag(cov_matrix)) * 100
        individual_sharpes = [(individual_returns[i] - risk_free_rate * 100) / individual_risks[i] if individual_risks[i] > 0 else 0 for i in range(n_assets)]
        
        best_sharpe_asset = ef_tickers_valid[np.argmax(individual_sharpes)]
        worst_sharpe_asset = ef_tickers_valid[np.argmin(individual_sharpes)]
        most_volatile = ef_tickers_valid[np.argmax(individual_risks)]
        
        # --- הצגת ציון כולל ---
        ai_score = min(100, max(0, int(
            efficiency_score * 0.35 +                    # 35% — יעילות מרקוביץ
            (100 - avg_corr * 100) * 0.25 +              # 25% — דיברסיפיקציה
            (100 - min(hhi / 30, 100)) * 0.20 +          # 20% — פיזור (לא מרוכז)
            min(my_return / max(opt_sharpe_ret, 1) * 100, 100) * 0.20  # 20% — תשואה
        )))
        
        # ציון ויזואלי
        score_col1, score_col2, score_col3 = st.columns([1, 2, 1])
        with score_col2:
            if ai_score >= 80:
                st.success(f"## 🏆 ציון תיק כולל: {ai_score}/100")
            elif ai_score >= 60:
                st.info(f"## 👍 ציון תיק כולל: {ai_score}/100")
            elif ai_score >= 40:
                st.warning(f"## ⚠️ ציון תיק כולל: {ai_score}/100")
            else:
                st.error(f"## 🔴 ציון תיק כולל: {ai_score}/100")
            st.progress(ai_score / 100)
        
        st.divider()
        
        # --- פירוט ציונים ---
        st.write("#### 📊 פירוט ציונים")
        
        scores_data = {
            "קטגוריה": [
                "🎯 יעילות מרקוביץ (Sharpe שלך vs אופטימלי)",
                "🔗 דיברסיפיקציה (מתאם ממוצע נמוך = טוב)",
                "📊 פיזור (אי-ריכוזיות — HHI)",
                "📈 תשואה צפויה (ביחס לאופטימום)"
            ],
            "ציון": [
                f"{efficiency_score:.0f}/100",
                f"{(100 - avg_corr * 100):.0f}/100",
                f"{max(0, 100 - hhi / 30):.0f}/100",
                f"{min(my_return / max(opt_sharpe_ret, 1) * 100, 100):.0f}/100"
            ],
            "פירוט": [
                f"Sharpe שלך: {my_sharpe:.2f} | אופטימלי: {opt_sharpe_val:.2f}",
                f"מתאם ממוצע: {avg_corr:.2f} | מקסימלי: {max_corr_val:.2f} | מינימלי: {min_corr_val:.2f}",
                f"HHI: {hhi:.0f} | 3 נכסים גדולים: {top3_weight:.1f}% מהתיק",
                f"תשואה שלך: {my_return:.2f}% | על החזית: {same_risk_ret:.2f}% | פער: {gap_return:+.2f}%"
            ]
        }
        st.table(pd.DataFrame(scores_data))
        
        st.divider()
        
        # --- מסקנות AI ---
        st.write("#### 🧠 מסקנות AI")
        
        conclusions = []
        
        # 1) יעילות מול החזית
        if gap_return <= 0.5 and gap_risk <= 0.5:
            conclusions.append(("success", "🏆 **התיק שלך על חזית היעילות!** ההקצאה הנוכחית כמעט אופטימלית — אתה מקבל את התשואה המקסימלית עבור רמת הסיכון שלך."))
        elif gap_return > 3:
            conclusions.append(("error", f"🔴 **פער יעילות משמעותי:** על אותו סיכון ({my_risk:.1f}%), החזית מאפשרת תשואה של **{same_risk_ret:.1f}%** במקום **{my_return:.1f}%** — אתה מפסיד **{gap_return:.1f}%** תשואה שנתית. שינוי באחוזי ההקצאה בלבד (בלי לקנות מניות חדשות) יכול לתקן את זה."))
        elif gap_return > 0.5:
            conclusions.append(("warning", f"⚠️ **פער יעילות קטן:** אתה מפסיד כ-**{gap_return:.1f}%** תשואה שנתית על אותו סיכון. לא דרמטי, אבל שווה לשקול אופטימיזציה."))
        
        if gap_risk > 3:
            conclusions.append(("warning", f"🛡️ **סיכון מיותר:** לתשואה של {my_return:.1f}%, אפשר להגיע עם σ={same_ret_risk:.1f}% במקום {my_risk:.1f}%. אתה לוקח **{gap_risk:.1f}% סיכון מיותר**."))
        
        # 2) דיברסיפיקציה
        if avg_corr > 0.6:
            conclusions.append(("error", f"🔴 **דיברסיפיקציה חלשה:** המתאם הממוצע בין הנכסים ({avg_corr:.2f}) גבוה מדי. הנכסים שלך נוטים לנוע יחד — מה שמבטל את יתרון הפיזור. שקול להוסיף נכסים עם מתאם נמוך (אגרות חוב, סחורות, שווקים מתעוררים)."))
        elif avg_corr > 0.4:
            conclusions.append(("warning", f"⚠️ **דיברסיפיקציה בינונית:** מתאם ממוצע {avg_corr:.2f}. יש מקום לשיפור — חפש נכסים עם מתאם נמוך יותר לשאר התיק."))
        else:
            conclusions.append(("success", f"✅ **דיברסיפיקציה טובה:** מתאם ממוצע {avg_corr:.2f} — הנכסים שלך מפוזרים היטב."))
        
        # 3) ריכוזיות
        if top3_weight > 80:
            conclusions.append(("error", f"🔴 **ריכוזיות גבוהה:** 3 הנכסים הגדולים מהווים **{top3_weight:.0f}%** מהתיק. אם אחד מהם ייפול — התיק כולו ייפגע קשות."))
        elif top3_weight > 60:
            conclusions.append(("warning", f"⚠️ **ריכוזיות בינונית:** 3 הנכסים הגדולים מהווים **{top3_weight:.0f}%** מהתיק."))
        else:
            conclusions.append(("success", f"✅ **פיזור טוב:** 3 הנכסים הגדולים מהווים רק **{top3_weight:.0f}%** מהתיק."))
        
        # 4) חשיפה לקריפטו
        crypto_weight = type_weights.get('Crypto', 0)
        if crypto_weight > 15:
            conclusions.append(("error", f"🔴 **חשיפת קריפטו גבוהה ({crypto_weight:.1f}%):** תנודתיות קיצונית. שקול להוריד ל-5-10% מהתיק."))
        elif crypto_weight > 10:
            conclusions.append(("warning", f"⚠️ **חשיפת קריפטו ({crypto_weight:.1f}%):** בטווח הגבוה. שמור עין על ירידות חדות."))
        elif crypto_weight > 0:
            conclusions.append(("info", f"ℹ️ **חשיפת קריפטו ({crypto_weight:.1f}%):** בטווח סביר לתיק עם אופי אגרסיבי."))
        
        # 5) נכס בעייתי
        worst_idx = np.argmin(individual_sharpes)
        worst_name = portfolio[ef_tickers_valid[worst_idx]]['name']
        worst_ret = individual_returns[worst_idx]
        worst_risk_val = individual_risks[worst_idx]
        worst_w = current_weights[worst_idx] * 100
        if individual_sharpes[worst_idx] < 0 and worst_w > 5:
            conclusions.append(("error", f"� **נכס בעייתי — {worst_name}:** Sharpe שלילי ({individual_sharpes[worst_idx]:.2f}). תשואה {worst_ret:.1f}% עם סיכון {worst_risk_val:.1f}%. המשקל שלו ({worst_w:.1f}%) גורר את התיק כלפי מטה."))
        elif individual_sharpes[worst_idx] < 0.3 and worst_w > 5:
            conclusions.append(("warning", f"⚠️ **נכס חלש — {worst_name}:** Sharpe נמוך ({individual_sharpes[worst_idx]:.2f}). שקול להקטין את המשקל ({worst_w:.1f}%)."))
        
        # 6) נכס חזק
        best_idx = np.argmax(individual_sharpes)
        best_name = portfolio[ef_tickers_valid[best_idx]]['name']
        best_w = current_weights[best_idx] * 100
        opt_best_w = opt_sharpe_w[best_idx] * 100
        if opt_best_w > best_w + 5:
            conclusions.append(("info", f"� **נכס חזק — {best_name}:** Sharpe הגבוה ביותר ({individual_sharpes[best_idx]:.2f}). המשקל האופטימלי ({opt_best_w:.1f}%) גבוה מהנוכחי ({best_w:.1f}%) — שקול להגדיל."))
        
        # 7) השוואה ל-type allocation
        core_w = type_weights.get('Core', 0)
        sat_w = type_weights.get('Satellite', 0)
        if core_w < 50:
            conclusions.append(("warning", f"⚠️ **ליבה נמוכה ({core_w:.0f}%):** אסטרטגיית Core/Satellite ממליצה על 70-80% ליבה. חשיפה נמוכה מדי לליבה מגדילה סיכון."))
        
        # הצגת כל המסקנות
        for msg_type, msg in conclusions:
            if msg_type == "success":
                st.success(msg)
            elif msg_type == "error":
                st.error(msg)
            elif msg_type == "warning":
                st.warning(msg)
            else:
                st.info(msg)
        
        st.divider()
        
        # --- המלצות פעולה ---
        st.write("#### 🔧 המלצות פעולה")
        
        actions = []
        
        # המלצות מבוססות על הפרשי משקלות
        increase = weights_df[weights_df['הפרש מ-Tangency'] > 3].sort_values('הפרש מ-Tangency', ascending=False)
        decrease = weights_df[weights_df['הפרש מ-Tangency'] < -3].sort_values('הפרש מ-Tangency')
        
        if not increase.empty:
            for _, row in increase.head(3).iterrows():
                diff_pct = row['הפרש מ-Tangency']
                actions.append(f"📈 **הגדל {row['שם']}** ({row['טיקר']}) מ-{row['שלי (%)']:.1f}% ל-{row['Tangency (%)']:.1f}% (+{diff_pct:.1f}%)")
        
        if not decrease.empty:
            for _, row in decrease.head(3).iterrows():
                diff_pct = abs(row['הפרש מ-Tangency'])
                actions.append(f"📉 **הקטן {row['שם']}** ({row['טיקר']}) מ-{row['שלי (%)']:.1f}% ל-{row['Tangency (%)']:.1f}% (-{diff_pct:.1f}%)")
        
        if gap_return > 1:
            actions.append(f"🎯 **צפי שיפור:** שינוי ההקצאה לפי ההמלצות למעלה צפוי להוסיף כ-**{gap_return:.1f}%** תשואה שנתית על אותו סיכון.")
        
        if gap_risk > 1:
            actions.append(f"🛡️ **או לחלופין:** שמור על אותה תשואה ({my_return:.1f}%) עם הורדת סיכון של **{gap_risk:.1f}%** בסטיית תקן.")
        
        if not actions:
            st.success("🏆 התיק שלך כבר מאוזן היטב — אין צורך בשינויים מהותיים!")
        else:
            for action in actions:
                st.markdown(f"• {action}")
        
        st.divider()
        
        # --- סיכום ---
        st.write("#### 📝 סיכום")
        
        summary_parts = []
        summary_parts.append(f"התיק שלך מורכב מ-**{n_assets} נכסים** עם תשואה צפויה של **{my_return:.2f}%** וסיכון (σ) של **{my_risk:.2f}%**.")
        summary_parts.append(f"ה-Sharpe Ratio שלך הוא **{my_sharpe:.2f}** (אופטימלי: {opt_sharpe_val:.2f}) — יעילות של **{efficiency_score:.0f}%**.")
        
        if gap_return > 0.5:
            summary_parts.append(f"על ידי שינוי האחוזים בלבד (בלי לקנות/למכור מניות חדשות), תוכל לקבל עוד **{gap_return:.1f}%** תשואה שנתית, או לחלופין להוריד **{gap_risk:.1f}%** מהסיכון.")
        else:
            summary_parts.append("התיק שלך קרוב מאוד לחזית היעילות — עבודה מצוינת!")
        
        st.info("\n\n".join(summary_parts))
        
        st.divider()
        st.caption(f"📊 מודל Markowitz (Mean-Variance Optimization) | אופטימיזציה: SciPy SLSQP | Rf = {risk_free_rate*100:.1f}% | נתונים היסטוריים אינם מבטיחים ביצועים עתידיים.")
    
    else:
        st.info("👆 לחץ על **'הרץ סימולציה'** כדי לחשב את חזית היעילות ולראות איפה התיק שלך נמצא!")
        
        st.markdown("""
        ### 🤔 מה זה חזית היעילות?
        
        **חזית היעילות (Efficient Frontier)** היא "חזית פארטו" של תיקי השקעות — הקו שמחבר את כל  
        ההרכבים שנותנים **תשואה מקסימלית** עבור רמת סיכון נתונה (או **סיכון מינימלי** עבור תשואה נתונה).
        
        #### איך זה עובד?
        תחשוב על זה כמו סגסוגת מתכות:
        - **הרכיבים קבועים** (אותן מניות שבתיק שלך)
        - **מה שמשתנה: האחוזים** (כמו שבר המסה של כל רכיב בסגסוגת)
        - **התכונות** (תשואה מול סיכון) משתנות **באופן לא-ליניארי** בגלל המתאם (Covariance) בין הנכסים
        
        #### מה יש בגרף?
        | סימן | משמעות |
        |-------|--------|
        | ענן נקודות | כל נקודה = הקצאה אחרת (אחוזים שונים, אותן מניות) |
        | **קו אדום** | חזית היעילות — אי אפשר לעשות טוב יותר |
        | **⭐** | איפה **אתה** עכשיו |
        | **💎** | Tangency Portfolio — Sharpe מקסימלי |
        | **🛡️** | GMV — סיכון מינימלי גלובלי |
        | חץ ירוק ↑ | כמה תשואה אתה "מפסיד" |
        | חץ כתום ← | כמה סיכון מיותר אתה לוקח |
        
        > 💡 אם **הנקודה שלך מתחת לקו האדום** — אתה יכול לשנות אחוזים בין הנכסים הקיימים  
        > ולקבל **יותר תשואה על אותו סיכון**, או **אותה תשואה עם פחות סיכון**.
        """)

# ==================== TAB 4: שיעורים פרטיים ====================
with tab4:
    st.title("📚 שיעורים פרטיים — מעקב הכנסות")

    # --- הגדרת תלמידים ---
    STUDENTS = {
        "ron":       {"name": "רון",          "emoji": "🧑‍🎓", "default_rate": 130},
        "shachar":   {"name": "שחר",          "emoji": "👩‍🎓", "default_rate": 150},
        "itay_adva": {"name": "איתי ואדווה", "emoji": "👫",  "default_rate": 120},
        "itamar":    {"name": "איתמר",        "emoji": "🧑‍🎓", "default_rate": 150},
    }

    # --- טעינת נתונים ---
    lessons_data = db.get_lessons_data({"lessons": [], "students": list(STUDENTS.keys())})
    if "lessons" not in lessons_data:
        lessons_data = {"lessons": [], "students": list(STUDENTS.keys())}
    # מיגרציה — מפתח ישן → חדש
    _migrated = False
    for _l in lessons_data.get("lessons", []):
        if _l.get("student") == "shachar_itay_adva":
            _l["student"] = "itay_adva"
            _migrated = True
    if _migrated:
        db.save_lessons_data(lessons_data)

    # --- הוספת שיעור חדש ---
    st.subheader("➕ הוסף שיעור חדש")

    add_cols = st.columns([2, 2, 2, 2, 1.5])
    with add_cols[0]:
        student_options = {k: f"{v['emoji']} {v['name']}" for k, v in STUDENTS.items()}
        selected_student = st.selectbox("תלמיד", options=list(student_options.keys()),
                                        format_func=lambda x: student_options[x], key="lesson_student")
    with add_cols[1]:
        lesson_date = st.date_input("תאריך", value=datetime.now().date(), key="lesson_date",
                                     min_value=datetime(2026, 1, 1).date())
    with add_cols[2]:
        input_mode = st.radio("שיטת חישוב", ["⏱️ שעות × מחיר", "💵 סכום קבוע"], horizontal=True, key="lesson_mode")
    
    if input_mode == "⏱️ שעות × מחיר":
        price_cols = st.columns([2, 2, 2])
        with price_cols[0]:
            duration_hours = st.number_input("משך (שעות)", min_value=0.25, max_value=10.0,
                                              value=1.0, step=0.25, key="lesson_dur")
        with price_cols[1]:
            _default_rate = float(STUDENTS[selected_student]["default_rate"])
            price_per_hour = st.number_input("מחיר לשעה (₪)", min_value=0.0,
                                              value=_default_rate, step=10.0, key="lesson_pph")
        with price_cols[2]:
            total_amount = duration_hours * price_per_hour
            st.metric("סה״כ", f"₪{total_amount:,.0f}")
    else:
        price_cols = st.columns([2, 2, 2])
        with price_cols[0]:
            total_amount = st.number_input("סכום סופי (₪)", min_value=0.0,
                                            value=100.0, step=10.0, key="lesson_fixed")
        with price_cols[1]:
            duration_hours = st.number_input("משך (שעות, אופציונלי)", min_value=0.0,
                                              max_value=10.0, value=0.0, step=0.25, key="lesson_dur_opt")
        with price_cols[2]:
            price_per_hour = (total_amount / duration_hours) if duration_hours > 0 else 0
            if price_per_hour > 0:
                st.metric("מחיר לשעה אפקטיבי", f"₪{price_per_hour:,.0f}")

    note_col, btn_col = st.columns([3, 1])
    with note_col:
        payment_method = st.radio("💳 אופן תשלום", ["bit", "paybox", "מזומן"],
                                   format_func=lambda x: {"bit": "📱 ביט", "paybox": "📲 פייבוקס", "מזומן": "💵 מזומן"}[x],
                                   horizontal=True, key="lesson_payment")
    with btn_col:
        st.markdown("<br>", unsafe_allow_html=True)
        add_lesson = st.button("✅ הוסף שיעור", key="add_lesson_btn", use_container_width=True)

    if add_lesson and total_amount > 0:
        new_lesson = {
            "student": selected_student,
            "date": lesson_date.strftime("%Y-%m-%d"),
            "duration": round(duration_hours, 2),
            "price_per_hour": round(price_per_hour, 2),
            "total": round(total_amount, 2),
            "payment": payment_method,
            "mode": "hours" if input_mode == "⏱️ שעות × מחיר" else "fixed",
        }
        lessons_data["lessons"].append(new_lesson)
        db.save_lessons_data(lessons_data)
        st.success(f"✅ נוסף שיעור ל-{STUDENTS[selected_student]['name']} — ₪{total_amount:,.0f}")
        st.rerun()
    elif add_lesson and total_amount <= 0:
        st.warning("⚠️ הסכום חייב להיות גדול מ-0")

    st.divider()

    # --- סיכום כללי KPIs ---
    all_lessons = lessons_data.get("lessons", [])

    if all_lessons:
        total_income = sum(l["total"] for l in all_lessons)
        total_hours = sum(l.get("duration", 0) for l in all_lessons)
        total_count = len(all_lessons)
        avg_per_hour = total_income / total_hours if total_hours > 0 else 0

        # סיכום לפי חודש נוכחי
        current_month = datetime.now().strftime("%Y-%m")
        month_lessons = [l for l in all_lessons if l["date"].startswith(current_month)]
        month_income = sum(l["total"] for l in month_lessons)
        month_hours = sum(l.get("duration", 0) for l in month_lessons)
        month_count = len(month_lessons)

        # חודש קודם — לחישוב טרנד
        _now = datetime.now()
        if _now.month == 1:
            _prev_month = f"{_now.year - 1}-12"
        else:
            _prev_month = f"{_now.year}-{_now.month - 1:02d}"
        prev_month_lessons = [l for l in all_lessons if l["date"].startswith(_prev_month)]
        prev_month_income = sum(l["total"] for l in prev_month_lessons)

        # תחזית שנתית — ממוצע חודשי × 12
        _months_set = set(l["date"][:7] for l in all_lessons)
        _num_months = max(len(_months_set), 1)
        monthly_avg = total_income / _num_months
        yearly_projection = monthly_avg * 12

        # --- שורה ראשונה: KPIs ראשיים ---
        kpi_cols = st.columns(5)
        kpi_cols[0].metric("💰 סה״כ הכנסות", f"₪{total_income:,.0f}")
        kpi_cols[1].metric("📅 שיעורים", f"{total_count}")
        kpi_cols[2].metric("⏱️ סה״כ שעות", f"{total_hours:,.1f}")
        kpi_cols[3].metric("� ממוצע לשעה", f"₪{avg_per_hour:,.0f}")

        # החודש + טרנד מול חודש קודם
        if prev_month_income > 0:
            _trend_pct = ((month_income - prev_month_income) / prev_month_income) * 100
            kpi_cols[4].metric(
                f"📆 החודש ({_now.strftime('%m/%Y')})",
                f"₪{month_income:,.0f}",
                delta=f"{_trend_pct:+.0f}% מול חודש קודם"
            )
        else:
            kpi_cols[4].metric(
                f"📆 החודש ({_now.strftime('%m/%Y')})",
                f"₪{month_income:,.0f} ({month_count})"
            )

        # --- שורה שנייה: תובנות נוספות ---
        kpi2_cols = st.columns(4)
        kpi2_cols[0].metric("📈 תחזית שנתית", f"₪{yearly_projection:,.0f}")
        kpi2_cols[1].metric("📊 ממוצע חודשי", f"₪{monthly_avg:,.0f}")
        kpi2_cols[2].metric("🕐 שעות החודש", f"{month_hours:,.1f}")

        # חלוקה לפי אמצעי תשלום
        _pay_totals = {}
        _pay_labels = {"bit": "📱 ביט", "paybox": "📲 פייבוקס", "מזומן": "💵 מזומן"}
        for l in all_lessons:
            _p = l.get('payment', l.get('note', 'לא ידוע'))
            _pay_totals[_p] = _pay_totals.get(_p, 0) + l["total"]
        _pay_str = " | ".join(f"{_pay_labels.get(k, k)}: ₪{v:,.0f}" for k, v in sorted(_pay_totals.items(), key=lambda x: -x[1]))
        kpi2_cols[3].metric("💳 לפי תשלום", "")
        kpi2_cols[3].caption(_pay_str)

        st.divider()

        # --- פירוט לפי תלמיד ---
        st.subheader("👨‍🏫 פירוט לפי תלמיד")

        for student_key, student_info in STUDENTS.items():
            student_lessons = [l for l in all_lessons if l["student"] == student_key]
            if not student_lessons:
                continue
            
            s_total = sum(l["total"] for l in student_lessons)
            s_hours = sum(l.get("duration", 0) for l in student_lessons)
            s_count = len(student_lessons)
            
            with st.expander(
                f"{student_info['emoji']} **{student_info['name']}** — "
                f"₪{s_total:,.0f} | {s_count} שיעורים | {s_hours:,.1f} שעות"
                f" | ₪{s_total / s_hours:,.0f}/שעה" if s_hours > 0 else
                f"{student_info['emoji']} **{student_info['name']}** — "
                f"₪{s_total:,.0f} | {s_count} שיעורים",
                expanded=True
            ):
                # טבלת שיעורים
                rows = []
                for i, l in enumerate(reversed(student_lessons)):
                    _pay = l.get('payment', l.get('note', '—'))
                    _pay_display = {"bit": "📱 ביט", "paybox": "📲 פייבוקס", "מזומן": "💵 מזומן"}.get(_pay, _pay)
                    row = {
                        '#': len(student_lessons) - i,
                        'תאריך': l['date'],
                        'משך': f"{l['duration']:.1f}h" if l.get('duration', 0) > 0 else "—",
                        'מחיר/שעה': f"₪{l['price_per_hour']:,.0f}" if l.get('price_per_hour', 0) > 0 else "—",
                        'סכום': f"₪{l['total']:,.0f}",
                        'תשלום': _pay_display,
                    }
                    rows.append(row)
                
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

                # --- מסקנות לתלמיד ---
                st.markdown("---")
                _s_avg_rate = s_total / s_hours if s_hours > 0 else 0
                _s_default_rate = float(student_info.get("default_rate", 0))
                _s_monthly_inc = {}
                for _sl in student_lessons:
                    _mk2 = _sl["date"][:7]
                    _s_monthly_inc[_mk2] = _s_monthly_inc.get(_mk2, 0) + _sl["total"]
                _s_num_months = max(len(_s_monthly_inc), 1)
                _s_monthly_avg = s_total / _s_num_months
                _s_proj_annual = _s_monthly_avg * 12
                _last_lesson_date = max(_sl["date"] for _sl in student_lessons)
                _last_dt = datetime.strptime(_last_lesson_date, "%Y-%m-%d")
                _days_since = (datetime.now() - _last_dt).days

                if s_count > 1:
                    _dates_sorted = sorted(datetime.strptime(_sl["date"], "%Y-%m-%d") for _sl in student_lessons)
                    _gaps = [(_dates_sorted[i+1] - _dates_sorted[i]).days for i in range(len(_dates_sorted)-1)]
                    _avg_gap_s = sum(_gaps) / len(_gaps)
                    _freq_per_month_s = 30 / _avg_gap_s if _avg_gap_s > 0 else 0
                else:
                    _avg_gap_s = None
                    _freq_per_month_s = None

                _sm_cols = st.columns(4)
                _sm_cols[0].metric("💰 הכנסה כוללת", f"₪{s_total:,.0f}")
                _sm_cols[1].metric("⏱️ שעות כולל", f"{s_hours:.1f}")
                _sm_cols[2].metric("📊 ממוצע חודשי", f"₪{_s_monthly_avg:,.0f}")
                _sm_cols[3].metric("📈 תחזית שנתית", f"₪{_s_proj_annual:,.0f}")

                _stips = []
                if _s_default_rate > 0 and _s_avg_rate > 0:
                    _rate_diff = _s_avg_rate - _s_default_rate
                    if abs(_rate_diff) < 5:
                        _stips.append(("success", f"✅ **תעריף תקין:** ₪{_s_avg_rate:.0f}/שעה — תואם את התעריף המוגדר (₪{_s_default_rate:.0f})."))
                    elif _rate_diff < 0:
                        _stips.append(("warning", f"⚠️ **תעריף ממוצע נמוך (₪{_s_avg_rate:.0f}/שעה)** לעומת תעריף בסיס ₪{_s_default_rate:.0f}. ייתכן שיש שיעורים שנרשמו בסכום שגוי."))
                    else:
                        _stips.append(("info", f"ℹ️ **תעריף ממוצע (₪{_s_avg_rate:.0f}/שעה)** מעל הבסיס (₪{_s_default_rate:.0f})."))

                if _days_since > 30:
                    _stips.append(("warning", f"📅 **השיעור האחרון לפני {_days_since} ימים** ({_last_lesson_date}). האם {student_info['name']} עדיין פעיל/ה?"))
                elif _days_since > 14:
                    _stips.append(("info", f"📅 **שיעור אחרון:** {_last_lesson_date} (לפני {_days_since} ימים)."))
                else:
                    _stips.append(("success", f"📅 **פעיל/ה:** שיעור אחרון לפני {_days_since} ימים ({_last_lesson_date})."))

                if _freq_per_month_s is not None:
                    if _freq_per_month_s < 1:
                        _stips.append(("warning", f"📉 **תדירות נמוכה ({_freq_per_month_s:.1f} שיעורים/חודש).** שיעור שבועי קבוע יוסיף ~₪{_s_default_rate * 4:,.0f}/חודש."))
                    elif _freq_per_month_s < 3:
                        _stips.append(("info", f"📊 **תדירות בינונית ({_freq_per_month_s:.1f} שיעורים/חודש)** — יש מקום להגדיל."))
                    else:
                        _stips.append(("success", f"✅ **תדירות טובה ({_freq_per_month_s:.1f} שיעורים/חודש).**"))

                _stips.append(("info", f"🔮 **תחזית שנתית מ{student_info['name']}:** ₪{_s_proj_annual:,.0f} (בהמשך קצב של ₪{_s_monthly_avg:,.0f}/חודש)."))

                for _st2, _sm2 in _stips:
                    if _st2 == "success": st.success(_sm2)
                    elif _st2 == "warning": st.warning(_sm2)
                    elif _st2 == "error": st.error(_sm2)
                    else: st.info(_sm2)

        st.divider()

        # --- גרף הכנסות לפי חודש ---
        st.subheader("📈 הכנסות לפי חודש")

        import plotly.express as px

        monthly_data = {}
        for l in all_lessons:
            month_key = l["date"][:7]  # "YYYY-MM"
            student_name = STUDENTS.get(l["student"], {}).get("name", l["student"])
            key = (month_key, student_name)
            monthly_data[key] = monthly_data.get(key, 0) + l["total"]

        if monthly_data:
            chart_rows = [{"חודש": k[0], "תלמיד": k[1], "סכום": v} for k, v in sorted(monthly_data.items())]
            chart_df = pd.DataFrame(chart_rows)
            fig = px.bar(chart_df, x="חודש", y="סכום", color="תלמיד",
                         text_auto=True, barmode="stack",
                         color_discrete_sequence=["#42a5f5", "#66bb6a", "#ffa726", "#ef5350"])
            fig.update_layout(
                yaxis_title="₪",
                xaxis_title="",
                legend_title="תלמיד",
                height=400,
            )
            fig.update_traces(texttemplate="₪%{y:,.0f}", textposition="inside")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # --- יעד הכנסה שנתית + טיפים כלכליים ---
        st.subheader("🎯 יעד הכנסה שנתית — ₪30,000")

        _GOAL_ANNUAL = 30000

        # --- חישובים ---
        # חודשים שנותרו בשנה הנוכחית
        _goal_now = datetime.now()
        _months_left = 12 - _goal_now.month + 1  # כולל החודש הנוכחי
        _income_this_year = sum(l["total"] for l in all_lessons if l["date"].startswith(str(_goal_now.year)))
        _remaining = max(_GOAL_ANNUAL - _income_this_year, 0)
        _goal_pct = min(_income_this_year / _GOAL_ANNUAL * 100, 100)

        # ממוצע נדרש לחודש כדי להגיע ליעד
        _needed_per_month = _remaining / max(_months_left, 1)

        # שיעורים נדרשים — לפי ממוצע הכנסה לשיעור
        _avg_per_lesson = total_income / total_count if total_count > 0 else 100
        _avg_duration = total_hours / total_count if total_count > 0 else 1.0
        _lessons_per_month_needed = _needed_per_month / _avg_per_lesson if _avg_per_lesson > 0 else 0
        _hours_per_month_needed = _lessons_per_month_needed * _avg_duration

        # שיעורים לשבוע
        _lessons_per_week_needed = _lessons_per_month_needed / 4.33

        # קצב נוכחי (שיעורים בחודש)
        _current_lessons_per_month = total_count / _num_months
        _current_hours_per_month = total_hours / _num_months

        # כמה צריך להגדיל
        _growth_needed = ((_lessons_per_month_needed - _current_lessons_per_month) / _current_lessons_per_month * 100) if _current_lessons_per_month > 0 else 0

        # --- Progress bar ---
        st.markdown(f"**התקדמות {_goal_now.year}:** ₪{_income_this_year:,.0f} מתוך ₪{_GOAL_ANNUAL:,.0f}")
        st.progress(min(_goal_pct / 100, 1.0))

        # --- KPIs של היעד ---
        gcol1, gcol2, gcol3, gcol4 = st.columns(4)
        gcol1.metric("✅ הושג", f"₪{_income_this_year:,.0f}", delta=f"{_goal_pct:.0f}%")
        gcol2.metric("🔴 חסר", f"₪{_remaining:,.0f}")
        gcol3.metric("📅 נדרש/חודש", f"₪{_needed_per_month:,.0f}")
        gcol4.metric("📆 חודשים נותרו", f"{_months_left}")

        st.markdown("")

        gcol5, gcol6, gcol7, gcol8 = st.columns(4)
        gcol5.metric("📚 שיעורים נדרשים/חודש", f"{_lessons_per_month_needed:.1f}")
        gcol6.metric("📅 שיעורים/שבוע", f"{_lessons_per_week_needed:.1f}")
        gcol7.metric("⏱️ שעות נדרשות/חודש", f"{_hours_per_month_needed:.1f}")
        gcol8.metric("📊 קצב נוכחי/חודש", f"{_current_lessons_per_month:.1f} שיעורים")

        # --- סטטוס היעד ---
        if _remaining <= 0:
            st.success(f"🏆 מזל טוב! הגעת ליעד ה-₪{_GOAL_ANNUAL:,.0f} השנה! סה״כ: ₪{_income_this_year:,.0f}")
        elif _growth_needed <= 0:
            st.success(f"✅ הקצב הנוכחי שלך ({_current_lessons_per_month:.1f} שיעורים/חודש) **מספיק** כדי להגיע ליעד! המשך ככה.")
        elif _growth_needed <= 20:
            st.info(f"👍 כמעט שם! צריך להגדיל ב-**{_growth_needed:.0f}%** — עוד {_lessons_per_month_needed - _current_lessons_per_month:.1f} שיעורים לחודש.")
        elif _growth_needed <= 50:
            st.warning(f"⚠️ צריך להגדיל את הקצב ב-**{_growth_needed:.0f}%** — מ-{_current_lessons_per_month:.1f} ל-{_lessons_per_month_needed:.1f} שיעורים/חודש.")
        else:
            st.error(f"🔴 פער גדול: צריך להגדיל ב-**{_growth_needed:.0f}%** — מ-{_current_lessons_per_month:.1f} ל-{_lessons_per_month_needed:.1f} שיעורים/חודש.")

        st.divider()

        # --- טיפים כלכליים מבוססי נתונים ---
        st.subheader("💡 מסקנות וטיפים כלכליים")

        tips = []

        # 1) ניתוח תעריף
        if avg_per_hour > 0:
            if avg_per_hour < 80:
                tips.append(("warning", f"💰 **תעריף נמוך (₪{avg_per_hour:.0f}/שעה):** שקול להעלות מחירים. שיעורים פרטיים איכותיים בשוק נעים בין ₪100-150/שעה. העלאה של ₪20/שעה תוסיף ₪{20 * _current_hours_per_month * 12:,.0f} בשנה."))
            elif avg_per_hour < 120:
                tips.append(("info", f"📊 **תעריף סביר (₪{avg_per_hour:.0f}/שעה).** אם התלמידים מרוצים ויש ביקוש — זה הזמן לשקול העלאה הדרגתית לתלמידים חדשים."))
            else:
                tips.append(("success", f"✅ **תעריף מצוין (₪{avg_per_hour:.0f}/שעה)!** אתה בטווח העליון — שמור על האיכות ותרחיב כמות תלמידים."))

        # 2) ניתוח תלמידים — מי הכי רווחי
        student_stats = {}
        for sk, si in STUDENTS.items():
            sl = [l for l in all_lessons if l["student"] == sk]
            if sl:
                s_inc = sum(l["total"] for l in sl)
                s_hrs = sum(l.get("duration", 0) for l in sl)
                s_rate = s_inc / s_hrs if s_hrs > 0 else 0
                student_stats[si["name"]] = {"income": s_inc, "hours": s_hrs, "rate": s_rate, "count": len(sl)}

        if len(student_stats) >= 2:
            best_student = max(student_stats.items(), key=lambda x: x[1]["rate"])
            worst_student = min(student_stats.items(), key=lambda x: x[1]["rate"])
            if best_student[1]["rate"] > worst_student[1]["rate"] * 1.3:
                tips.append(("info", f"📈 **{best_student[0]}** הוא התלמיד הרווחי ביותר (₪{best_student[1]['rate']:.0f}/שעה), "
                             f"בעוד **{worst_student[0]}** מניב ₪{worst_student[1]['rate']:.0f}/שעה. "
                             f"שקול לנהל משא ומתן על תעריף עם תלמידים בתעריף נמוך."))

        # 3) ניתוח עקביות
        _monthly_incomes = {}
        for l in all_lessons:
            mk = l["date"][:7]
            _monthly_incomes[mk] = _monthly_incomes.get(mk, 0) + l["total"]
        
        if len(_monthly_incomes) >= 2:
            _month_values = list(_monthly_incomes.values())
            _month_std = (sum((x - monthly_avg) ** 2 for x in _month_values) / len(_month_values)) ** 0.5
            _cv = _month_std / monthly_avg * 100 if monthly_avg > 0 else 0
            if _cv > 50:
                tips.append(("warning", f"📉 **הכנסה לא יציבה:** הפער בין החודשים גדול ({_cv:.0f}% CV). נסה לקבוע שיעורים קבועים שבועיים כדי לייצב."))
            elif _cv > 25:
                tips.append(("info", f"📊 **הכנסה בינונית ביציבות** ({_cv:.0f}% CV). תוכנית שבועית קבועה תעזור."))
            else:
                tips.append(("success", f"✅ **הכנסה יציבה!** ({_cv:.0f}% CV) — יציבות מעולה בין החודשים."))

        # 4) ניתוח אמצעי תשלום
        _cash_pct = _pay_totals.get("מזומן", 0) / total_income * 100 if total_income > 0 else 0
        if _cash_pct > 40:
            tips.append(("warning", f"💵 **{_cash_pct:.0f}% מההכנסות במזומן.** שקול לעבור לתשלום דיגיטלי (ביט/פייבוקס) — קל יותר לתעד, בטוח יותר, ושקוף יותר למס."))

        # 5) העלאת מחיר — סימולציה
        if avg_per_hour > 0 and total_hours > 0:
            _extra_10 = 10 * (_current_hours_per_month * 12)  # תוספת של ₪10/שעה לכל שיעור
            _extra_20 = 20 * (_current_hours_per_month * 12)
            tips.append(("info", f"🧮 **סימולציית העלאת מחיר:** העלאה של ₪10/שעה = +₪{_extra_10:,.0f}/שנה. "
                         f"העלאה של ₪20/שעה = +₪{_extra_20:,.0f}/שנה. (בהנחת {_current_hours_per_month:.0f} שעות/חודש)"))

        # 6) תלמיד נוסף — סימולציה
        if _current_lessons_per_month > 0:
            _extra_student = avg_per_hour * _avg_duration * 4 * 12  # תלמיד נוסף, פעם בשבוע
            tips.append(("info", f"👤 **תלמיד נוסף (שיעור/שבוע):** יוסיף כ-₪{_extra_student:,.0f}/שנה "
                         f"(בתעריף ₪{avg_per_hour:.0f}/שעה, {_avg_duration:.1f}ש׳ לשיעור)."))

        # 7) יעד 30K — ספציפי
        if yearly_projection < _GOAL_ANNUAL:
            _gap_annual = _GOAL_ANNUAL - yearly_projection
            _need_extra_hours = _gap_annual / avg_per_hour / 12 if avg_per_hour > 0 else 0
            tips.append(("warning", f"🎯 **ליעד ₪{_GOAL_ANNUAL:,.0f}:** חסרים ₪{_gap_annual:,.0f}/שנה (₪{_gap_annual/12:,.0f}/חודש). "
                         f"הדרך: עוד **{_need_extra_hours:.1f} שעות/חודש**, "
                         f"או **העלאת תעריף ל-₪{_GOAL_ANNUAL / (_current_hours_per_month * 12):,.0f}/שעה** (ללא שינוי בכמות)."))
        else:
            tips.append(("success", f"🎯 **התחזית השנתית (₪{yearly_projection:,.0f}) עומדת ביעד ₪{_GOAL_ANNUAL:,.0f}!** אפשר לשאוף ל-₪40,000 😎"))

        # הצגת הטיפים
        for _tip_type, _tip_msg in tips:
            if _tip_type == "success":
                st.success(_tip_msg)
            elif _tip_type == "warning":
                st.warning(_tip_msg)
            elif _tip_type == "error":
                st.error(_tip_msg)
            else:
                st.info(_tip_msg)

        st.divider()

        # --- תחזית עתידית חודש-חודש ---
        st.subheader("🔮 תחזית עתידית — 2026")

        _fc_now = datetime.now()
        _fc_year = _fc_now.year
        _all_year_months = [f"{_fc_year}-{m:02d}" for m in range(1, 13)]

        # הכנסות בפועל לפי חודש בשנה הנוכחית
        _actual_by_month = {}
        for _fl in all_lessons:
            if _fl["date"].startswith(str(_fc_year)):
                _mk3 = _fl["date"][:7]
                _actual_by_month[_mk3] = _actual_by_month.get(_mk3, 0) + _fl["total"]

        # בניית טבלת תחזית
        _fc_rows = []
        for _fc_m in _all_year_months:
            _fc_m_dt = datetime.strptime(_fc_m + "-01", "%Y-%m-%d")
            if _fc_m in _actual_by_month:
                _fc_rows.append({"חודש": _fc_m, "סכום": _actual_by_month[_fc_m], "סוג": "בפועל"})
            elif _fc_m_dt.month >= _fc_now.month:
                _fc_rows.append({"חודש": _fc_m, "סכום": monthly_avg, "סוג": "תחזית"})

        if _fc_rows:
            _fc_df = pd.DataFrame(_fc_rows)
            _fc_actual_sum = _fc_df[_fc_df["סוג"] == "בפועל"]["סכום"].sum()
            _fc_projected_sum = _fc_df[_fc_df["סוג"] == "תחזית"]["סכום"].sum()
            _fc_total = _fc_actual_sum + _fc_projected_sum

            _fc_kpi = st.columns(4)
            _fc_kpi[0].metric("✅ בפועל 2026", f"₪{_fc_actual_sum:,.0f}")
            _fc_kpi[1].metric("🔮 תחזית יתרת השנה", f"₪{_fc_projected_sum:,.0f}")
            _fc_kpi[2].metric("📊 סה״כ צפוי 2026", f"₪{_fc_total:,.0f}")
            _fc_goal_delta = _fc_total - _GOAL_ANNUAL
            _fc_kpi[3].metric(
                f"🎯 מול יעד ₪{_GOAL_ANNUAL:,}",
                f"{'✅ עומד ביעד' if _fc_goal_delta >= 0 else '❌ לא עומד'}",
                delta=f"{_fc_goal_delta:+,.0f}₪"
            )

            _fc_fig = px.bar(
                _fc_df, x="חודש", y="סכום", color="סוג",
                color_discrete_map={"בפועל": "#42a5f5", "תחזית": "#b0bec5"},
                text_auto=True,
            )
            _fc_fig.add_hline(
                y=_GOAL_ANNUAL / 12, line_dash="dash", line_color="#ef5350",
                annotation_text=f"יעד חודשי ₪{_GOAL_ANNUAL/12:,.0f}",
                annotation_position="top right"
            )
            _fc_fig.update_layout(
                yaxis_title="₪", xaxis_title="", legend_title="", height=380,
                showlegend=True,
            )
            _fc_fig.update_traces(texttemplate="₪%{y:,.0f}", textposition="outside")
            st.plotly_chart(_fc_fig, use_container_width=True)

            if _fc_total >= _GOAL_ANNUAL:
                st.success(f"🏆 **תחזית {_fc_year}: ₪{_fc_total:,.0f}** — עומד ביעד ₪{_GOAL_ANNUAL:,}! כל הכבוד!")
            else:
                _fc_gap = _GOAL_ANNUAL - _fc_total
                _fc_months_left = max(12 - _fc_now.month, 1)
                _fc_extra_hours = _fc_gap / avg_per_hour / _fc_months_left if avg_per_hour > 0 else 0
                st.warning(
                    f"📊 **תחזית {_fc_year}: ₪{_fc_total:,.0f}** — חסרים ₪{_fc_gap:,.0f} ליעד. "
                    f"כדי לסגור את הפער: עוד **{_fc_extra_hours:.1f} שעות/חודש** עד סוף השנה, "
                    f"או העלאת תעריף ב-₪{_fc_gap / (total_hours if total_hours > 0 else 1):.0f}/שעה על כל השיעורים הנותרים."
                )

        st.divider()

        # --- עריכת שיעור ---
        st.subheader("✏️ עריכת שיעור")

        if all_lessons:
            edit_options = []
            for i, l in enumerate(all_lessons):
                s_name = STUDENTS.get(l["student"], {}).get("name", l["student"])
                _pay = l.get('payment', l.get('note', ''))
                _pay_d = {"bit": "ביט", "paybox": "פייבוקס", "מזומן": "מזומן"}.get(_pay, _pay)
                edit_options.append(
                    f"#{i+1} | {l['date']} | {s_name} | ₪{l['total']:,.0f} | {_pay_d}"
                )

            selected_edit = st.selectbox("בחר שיעור לעריכה", edit_options, key="edit_lesson_select")
            edit_idx = edit_options.index(selected_edit)
            edit_lesson = all_lessons[edit_idx]

            _pay_options = ["bit", "paybox", "מזומן"]
            _current_pay = edit_lesson.get('payment', edit_lesson.get('note', 'bit'))
            _pay_idx = _pay_options.index(_current_pay) if _current_pay in _pay_options else 0

            ec1, ec2, ec3, ec4 = st.columns(4)
            with ec1:
                new_duration = st.number_input("משך (שעות)", min_value=0.0, max_value=10.0,
                                                value=float(edit_lesson.get('duration', 0)),
                                                step=0.25, key="edit_dur")
            with ec2:
                new_pph = st.number_input("מחיר לשעה (₪)", min_value=0.0,
                                           value=float(edit_lesson.get('price_per_hour', 0)),
                                           step=10.0, key="edit_pph")
            with ec3:
                _auto_total = round(new_duration * new_pph, 2) if (new_duration > 0 and new_pph > 0) else float(edit_lesson.get('total', 0))
                new_total = st.number_input("סכום סופי (₪)", min_value=0.0,
                                             value=_auto_total,
                                             step=10.0, key="edit_total")
            with ec4:
                new_payment = st.radio("תשלום", _pay_options,
                                        format_func=lambda x: {"bit": "📱 ביט", "paybox": "📲 פייבוקס", "מזומן": "💵 מזומן"}[x],
                                        index=_pay_idx, horizontal=True, key="edit_payment")

            if st.button("💾 שמור שינויים", key="save_edit_btn"):
                lessons_data["lessons"][edit_idx]["duration"] = round(new_duration, 2)
                lessons_data["lessons"][edit_idx]["price_per_hour"] = round(new_pph, 2)
                lessons_data["lessons"][edit_idx]["total"] = round(new_total, 2)
                lessons_data["lessons"][edit_idx]["payment"] = new_payment
                if new_duration > 0 and new_total > 0:
                    lessons_data["lessons"][edit_idx]["price_per_hour"] = round(new_total / new_duration, 2)
                db.save_lessons_data(lessons_data)
                st.success("✅ השיעור עודכן בהצלחה!")
                st.rerun()

        st.divider()

        # --- מחיקת שיעור ---
        st.subheader("🗑️ מחיקת שיעור")
        st.caption("בחר שיעור למחיקה (במקרה של טעות)")

        if all_lessons:
            delete_options = []
            for i, l in enumerate(all_lessons):
                s_name = STUDENTS.get(l["student"], {}).get("name", l["student"])
                _pay = l.get('payment', l.get('note', ''))
                _pay_d = {"bit": "ביט", "paybox": "פייבוקס", "מזומן": "מזומן"}.get(_pay, _pay)
                delete_options.append(
                    f"#{i+1} | {l['date']} | {s_name} | ₪{l['total']:,.0f} | {_pay_d}"
                )
            
            del_col1, del_col2 = st.columns([4, 1])
            with del_col1:
                selected_delete = st.selectbox("בחר שיעור", delete_options, key="delete_lesson_select")
            with del_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ מחק", key="delete_lesson_btn", use_container_width=True):
                    idx = delete_options.index(selected_delete)
                    deleted = lessons_data["lessons"].pop(idx)
                    db.save_lessons_data(lessons_data)
                    s_name = STUDENTS.get(deleted["student"], {}).get("name", deleted["student"])
                    st.success(f"🗑️ נמחק: {s_name} — {deleted['date']} — ₪{deleted['total']:,.0f}")
                    st.rerun()

    else:
        st.info("🎒 אין שיעורים עדיין. התחל להוסיף שיעורים למעלה!")
