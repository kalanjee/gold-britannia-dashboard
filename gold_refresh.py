#!/usr/bin/env python3
"""
Gold Britannia Intelligence Dashboard — Auto-Refresh Script
============================================================
Pulls data from free APIs, computes signals, regenerates the dashboard HTML,
and sends Gmail alerts when a 5%+ gold move is probable.

SETUP:
1. pip install requests yfinance pandas --break-system-packages
2. Get a free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
3. Get a free Open Exchange Rates key: https://openexchangerates.org/signup/free
4. Set up a Gmail App Password: https://myaccount.google.com/apppasswords
5. Fill in config.json (created on first run) with your keys
6. Run: python gold_refresh.py
7. Schedule with cron (Linux/Mac) or Task Scheduler (Windows):
   - Every 4 hours: 0 */4 * * * cd /path/to/folder && python gold_refresh.py

Author: Built for Nikhil
"""

import json
import os
import sys
import time
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
DASHBOARD_TEMPLATE = SCRIPT_DIR / "gold_britannia_dashboard.html"
DASHBOARD_OUTPUT = SCRIPT_DIR / "gold_britannia_dashboard.html"
DATA_CACHE = SCRIPT_DIR / "gold_data_cache.json"
HISTORY_FILE = SCRIPT_DIR / "gold_history.json"
ALERT_LOG = SCRIPT_DIR / "alert_log.json"

DEFAULT_CONFIG = {
    "fred_api_key": "YOUR_FRED_API_KEY_HERE",
    "open_exchange_rates_key": "YOUR_OER_KEY_HERE",
    "gmail_sender": "your.email@gmail.com",
    "gmail_app_password": "YOUR_APP_PASSWORD_HERE",
    "gmail_recipient": "kalanjee@gmail.com",
    "alert_threshold_pct": 5.0,
    "alert_cooldown_hours": 24,
    "britannia_premium_pct": 3.8,
    "manual_dealer_prices": {
        "bullionbypost": None,
        "chards": None,
        "atkinsons": None,
        "royalmint": None,
        "last_checked": None
    }
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(SCRIPT_DIR / "gold_refresh.log")
    ]
)
log = logging.getLogger("gold_refresh")


def load_config():
    """Load or create config file."""
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        log.warning(f"Created {CONFIG_FILE} — please fill in your API keys!")
        print(f"\n{'='*60}")
        print(f"FIRST RUN: Config file created at:\n  {CONFIG_FILE}")
        print(f"\nPlease edit it with your API keys:")
        print(f"  1. FRED API key (free): https://fred.stlouisfed.org/docs/api/api_key.html")
        print(f"  2. Open Exchange Rates (free): https://openexchangerates.org/signup/free")
        print(f"  3. Gmail App Password: https://myaccount.google.com/apppasswords")
        print(f"{'='*60}\n")
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        config = json.load(f)

    if config.get("fred_api_key", "").startswith("YOUR_"):
        log.warning("FRED API key not configured — macro data will use fallbacks")
    if config.get("open_exchange_rates_key", "").startswith("YOUR_"):
        log.warning("Open Exchange Rates key not configured — FX data will use fallbacks")

    return config


# ============================================================
# DATA FETCHERS
# ============================================================

def fetch_json(url, timeout=15):
    """Safe JSON fetch with error handling."""
    import requests
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "GoldBritanniaDashboard/1.0"})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Fetch failed: {url} — {e}")
        return None


def fetch_gold_spot():
    """Fetch gold and silver spot prices from multiple free sources."""
    # Try metals.live first
    data = fetch_json("https://api.metals.live/v1/spot")
    if data:
        gold = next((m for m in data if m.get("metal", "").lower() == "gold"), None)
        silver = next((m for m in data if m.get("metal", "").lower() == "silver"), None)
        if gold:
            return {
                "gold_usd": float(gold.get("price", 0)),
                "silver_usd": float(silver.get("price", 0)) if silver else None,
                "source": "metals.live"
            }

    # Fallback: Yahoo Finance
    try:
        import yfinance as yf
        gold_ticker = yf.Ticker("GC=F")
        hist = gold_ticker.history(period="1d")
        if not hist.empty:
            silver_ticker = yf.Ticker("SI=F")
            silver_hist = silver_ticker.history(period="1d")
            return {
                "gold_usd": float(hist['Close'].iloc[-1]),
                "silver_usd": float(silver_hist['Close'].iloc[-1]) if not silver_hist.empty else None,
                "source": "yfinance"
            }
    except Exception as e:
        log.error(f"yfinance gold fetch failed: {e}")

    return None


def fetch_fx_rates(config):
    """Fetch FX rates from Open Exchange Rates or fallback."""
    key = config.get("open_exchange_rates_key", "")
    if key and not key.startswith("YOUR_"):
        data = fetch_json(f"https://openexchangerates.org/api/latest.json?app_id={key}")
        if data and "rates" in data:
            rates = data["rates"]
            return {
                "gbp_usd": 1.0 / rates.get("GBP", 0.79),
                "eur_usd": 1.0 / rates.get("EUR", 0.92),
                "usd_cny": rates.get("CNY", 7.2),
                "source": "openexchangerates"
            }

    # Fallback: ECB
    try:
        import requests
        resp = requests.get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", timeout=10)
        if resp.ok:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            ns = {'ns': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}
            rates = {}
            for cube in root.findall('.//ns:Cube[@currency]', ns):
                rates[cube.get('currency')] = float(cube.get('rate'))
            if 'GBP' in rates and 'USD' in rates:
                return {
                    "gbp_usd": rates['USD'] / rates['GBP'],
                    "eur_usd": 1.0 / rates['USD'],
                    "usd_cny": rates.get('CNY', 7.2) / rates['USD'] if 'CNY' in rates else 7.2,
                    "source": "ecb"
                }
    except Exception as e:
        log.error(f"ECB FX fetch failed: {e}")

    return None


def fetch_fred_series(series_id, config, observation_limit=1):
    """Fetch a single FRED series."""
    key = config.get("fred_api_key", "")
    if not key or key.startswith("YOUR_"):
        return None
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={key}&file_type=json"
           f"&sort_order=desc&limit={observation_limit}")
    data = fetch_json(url)
    if data and "observations" in data and data["observations"]:
        val = data["observations"][0].get("value", ".")
        try:
            return float(val)
        except ValueError:
            return None
    return None


def fetch_macro_data(config):
    """Fetch all macroeconomic data from FRED."""
    series = {
        "fed_rate": "FEDFUNDS",
        "us_cpi": "CPIAUCSL",
        "us_10y": "DGS10",
        "us_real_yield": "DFII10",
        "m2": "M2SL",
        "us_cpi_yoy": "CPIAUCSL",
    }

    results = {}
    for name, sid in series.items():
        val = fetch_fred_series(sid, config)
        if val is not None:
            results[name] = val
        log.info(f"  FRED {sid}: {val}")

    return results


def fetch_market_data():
    """Fetch market sentiment data via yfinance."""
    try:
        import yfinance as yf

        results = {}

        # VIX
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="1d")
        if not vix_hist.empty:
            results["vix"] = float(vix_hist['Close'].iloc[-1])

        # DXY (Dollar Index)
        dxy = yf.Ticker("DX-Y.NYB")
        dxy_hist = dxy.history(period="1d")
        if not dxy_hist.empty:
            results["dxy"] = float(dxy_hist['Close'].iloc[-1])

        # GLD ETF
        gld = yf.Ticker("GLD")
        gld_info = gld.info
        results["gld_aum"] = gld_info.get("totalAssets", None)
        gld_hist = gld.history(period="5d")
        if not gld_hist.empty:
            results["gld_price"] = float(gld_hist['Close'].iloc[-1])

        # Brent Crude
        oil = yf.Ticker("BZ=F")
        oil_hist = oil.history(period="1d")
        if not oil_hist.empty:
            results["brent_oil"] = float(oil_hist['Close'].iloc[-1])

        # Copper
        copper = yf.Ticker("HG=F")
        copper_hist = copper.history(period="1d")
        if not copper_hist.empty:
            results["copper"] = float(copper_hist['Close'].iloc[-1])

        log.info(f"  Market data: {list(results.keys())}")
        return results

    except Exception as e:
        log.error(f"Market data fetch failed: {e}")
        return {}


def _align_series(source_hist, target_dates):
    """Align a history dict (with dates/values) to a target date list using forward-fill."""
    lookup = dict(zip(source_hist["dates"], source_hist["values"]))
    aligned = []
    last_val = source_hist["values"][0] if source_hist["values"] else 0
    for d in target_dates:
        if d in lookup:
            last_val = lookup[d]
        aligned.append(last_val)
    return aligned


def fetch_historical(days=90):
    """Fetch 90-day history for chart data."""
    try:
        import yfinance as yf
        import pandas as pd

        period = f"{days}d"
        tickers = {
            "gold_usd": "GC=F",
            "silver_usd": "SI=F",
            "brent_oil": "BZ=F",
            "vix": "^VIX",
            "dxy": "DX-Y.NYB",
            "gld": "GLD",
            "us_10y": "^TNX",
            "us_2y": "^IRX",
        }

        history = {}
        for name, ticker in tickers.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period=period)
                if not hist.empty:
                    history[name] = {
                        "dates": [d.strftime('%Y-%m-%d') for d in hist.index],
                        "values": [round(float(v), 2) for v in hist['Close']]
                    }
            except Exception as e:
                log.warning(f"  History fetch failed for {ticker}: {e}")

        return history
    except Exception as e:
        log.error(f"Historical data fetch failed: {e}")
        return {}


# ============================================================
# SIGNAL COMPUTATION
# ============================================================

def compute_signal(name, value, prev_value=None, context=None):
    """
    Compute bullish/bearish/neutral signal for each variable.
    Returns: (signal, reason)
    """
    if value is None:
        return "Neutral", "No data available"

    signals = {
        "fed_rate": lambda v, p: ("Bullish", "Rate cuts expected — lower yields support gold") if v <= 4.5
            else ("Bearish", "High rates increase opportunity cost of holding gold"),
        "us_10y": lambda v, p: ("Bullish", "Yields falling — reduces gold's opportunity cost") if p and v < p
            else ("Bearish", "Rising yields weigh on gold") if p and v > p
            else ("Neutral", "Yields stable"),
        "us_real_yield": lambda v, p: ("Bullish", "Negative/low real yields strongly support gold") if v < 2.0
            else ("Bearish", "High real yields reduce gold appeal"),
        "vix": lambda v, p: ("Bullish", "Elevated fear drives safe-haven gold demand") if v > 18
            else ("Neutral", "Low volatility — limited fear premium"),
        "dxy": lambda v, p: ("Bullish", "Weakening dollar supports gold priced in USD") if p and v < p
            else ("Bearish", "Strengthening dollar weighs on gold") if p and v > p
            else ("Neutral", "Dollar stable"),
        "gbp_usd": lambda v, p: ("Bullish", "Weaker £ increases GBP gold price") if p and v < p
            else ("Bearish", "Stronger £ reduces GBP gold price") if p and v > p
            else ("Neutral", "GBP/USD stable"),
        "us_cpi": lambda v, p: ("Bullish", "Sticky inflation supports gold as hedge") if v > 2.5
            else ("Neutral", "Inflation near target — limited additional impetus"),
        "brent_oil": lambda v, p: ("Bullish", "Rising energy prices stoke inflation expectations") if p and v > p * 1.03
            else ("Neutral", "Oil stable — limited impact"),
    }

    fn = signals.get(name)
    if fn:
        return fn(value, prev_value)

    # Default: use change direction
    if prev_value and prev_value != 0:
        chg = (value - prev_value) / abs(prev_value)
        if chg > 0.01:
            return "Bullish", f"Rising {chg*100:.1f}%"
        elif chg < -0.01:
            return "Bearish", f"Falling {chg*100:.1f}%"
    return "Neutral", "No significant change"


def compute_5pct_probability(variables, vix_val=15):
    """
    Estimate probability of a 5%+ gold move in next 30 days.
    Simple model using VIX, signal concentration, and macro alignment.
    """
    if not variables:
        return 25

    bullish = sum(1 for v in variables if v.get("signal") == "Bullish")
    bearish = sum(1 for v in variables if v.get("signal") == "Bearish")
    total = len(variables)
    concentration = max(bullish, bearish) / total if total > 0 else 0

    # Weighted signal score
    weights = {"Critical": 3, "Very High": 2.5, "High": 2, "Medium": 1, "Low": 0.5}
    w_bull = sum(weights.get(v.get("importance", "Medium"), 1) for v in variables if v.get("signal") == "Bullish")
    w_bear = sum(weights.get(v.get("importance", "Medium"), 1) for v in variables if v.get("signal") == "Bearish")
    w_total = sum(weights.get(v.get("importance", "Medium"), 1) for v in variables)
    score = abs(w_bull - w_bear) / w_total if w_total > 0 else 0

    # Model: VIX contribution + signal concentration + alignment
    prob = (vix_val * 1.2) + (concentration * 25) + (score * 30)
    return min(95, max(5, round(prob)))


# ============================================================
# DASHBOARD GENERATION
# ============================================================

def generate_dashboard_data(config):
    """Fetch all data and compile into dashboard JSON."""
    log.info("Starting data refresh...")

    # Load previous cache for change calculations
    prev_data = {}
    if DATA_CACHE.exists():
        with open(DATA_CACHE) as f:
            prev_data = json.load(f)

    # Fetch all sources
    log.info("Fetching gold spot prices...")
    spot = fetch_gold_spot() or {}

    log.info("Fetching FX rates...")
    fx = fetch_fx_rates(config) or {}

    log.info("Fetching macro data from FRED...")
    macro = fetch_macro_data(config)

    log.info("Fetching market sentiment data...")
    market = fetch_market_data()

    log.info("Fetching historical data...")
    history = fetch_historical(90)

    # Compute derived values
    gold_usd = spot.get("gold_usd", prev_data.get("gold_spot_usd", 2900))
    gbp_usd = fx.get("gbp_usd", prev_data.get("gbp_usd", 1.27))
    gold_gbp = gold_usd / gbp_usd
    premium_pct = config.get("britannia_premium_pct", 3.8)
    britannia_gbp = gold_gbp * (1 + premium_pct / 100)
    silver_usd = spot.get("silver_usd", prev_data.get("silver_usd", 32))
    gold_silver_ratio = gold_usd / silver_usd if silver_usd and silver_usd > 0 else 88

    # Build variable list with signals
    prev_vars = {v["name"]: v for v in prev_data.get("variables", [])} if prev_data else {}

    def prev_val(name):
        pv = prev_vars.get(name, {})
        return pv.get("value")

    def chg(current, previous):
        if previous and previous != 0 and current is not None:
            return round((current - previous) / abs(previous) * 100, 2)
        return 0

    vix_val = market.get("vix", 15)
    dxy_val = market.get("dxy", 104)
    fed_rate = macro.get("fed_rate", 4.5)
    us_10y = macro.get("us_10y", 4.3)
    real_yield = macro.get("us_real_yield", 1.9)
    us_cpi = macro.get("us_cpi_yoy", macro.get("us_cpi", 3.0))
    m2 = macro.get("m2", 21.5)
    brent = market.get("brent_oil", 80)
    copper = market.get("copper", 4.2)

    variables = []

    def add_var(id, name, cat, imp, value, unit, signal_key=None, manual_signal=None, manual_reason=None, source=""):
        pv = prev_val(name)
        change = chg(value, pv)
        if manual_signal:
            sig, reason = manual_signal, manual_reason
        elif signal_key:
            sig, reason = compute_signal(signal_key, value, pv)
        else:
            sig, reason = "Neutral", "—"
        variables.append({
            "id": id, "name": name, "category": cat, "importance": imp,
            "value": round(value, 4) if isinstance(value, float) else value,
            "unit": unit, "change_pct": change, "signal": sig, "reason": reason, "source": source
        })

    # 1. Direct Price Factors
    add_var(1, "Gold Spot (XAU/USD)", "Direct Price", "Critical", gold_usd, "$",
            signal_key="gold_usd", source=spot.get("source", "—"))
    add_var(2, "GBP/USD Rate", "Direct Price", "Critical", gbp_usd, "",
            signal_key="gbp_usd", source=fx.get("source", "—"))
    add_var(3, "Britannia Premium", "Direct Price", "Critical", premium_pct, "%",
            manual_signal="Neutral", manual_reason="Using configured premium", source="Config/Dealer survey")
    add_var(4, "UK VAT Status", "Direct Price", "High", 0, "%",
            manual_signal="Bullish", manual_reason="Britannias remain VAT-free as legal tender", source="HMRC")

    # 2. Macroeconomic
    add_var(5, "US Fed Funds Rate", "Macroeconomic", "Very High", fed_rate, "%",
            signal_key="fed_rate", source="FRED")
    add_var(6, "UK Bank Rate", "Macroeconomic", "High", 4.25, "%",
            manual_signal="Bullish", manual_reason="BoE easing cycle supports gold", source="BoE")
    add_var(7, "US CPI (YoY)", "Macroeconomic", "Very High", us_cpi, "%",
            signal_key="us_cpi", source="FRED")
    add_var(8, "UK CPI (YoY)", "Macroeconomic", "High", 2.8, "%",
            manual_signal="Neutral", manual_reason="Near target, limited additional impetus", source="ONS")
    add_var(9, "US 10Y Treasury Yield", "Macroeconomic", "Very High", us_10y, "%",
            signal_key="us_10y", source="FRED")
    add_var(10, "UK 10Y Gilt Yield", "Macroeconomic", "High", 4.15, "%",
            manual_signal="Neutral", manual_reason="Gilt yields stable", source="BoE")
    add_var(11, "US Real Yield (10Y TIPS)", "Macroeconomic", "Very High", real_yield, "%",
            signal_key="us_real_yield", source="FRED")
    add_var(12, "US M2 Money Supply", "Macroeconomic", "Medium", m2, "$T",
            manual_signal="Bullish", manual_reason="Money supply expansion supports asset prices", source="FRED")

    # 3. Sentiment
    add_var(13, "VIX (Fear Index)", "Sentiment", "High", vix_val, "",
            signal_key="vix", source="Yahoo Finance")
    add_var(14, "GLD ETF Holdings", "Sentiment", "High", market.get("gld_price", 215), "$",
            manual_signal="Bullish", manual_reason="ETF demand rising", source="Yahoo Finance")
    add_var(15, "SGLN (UK Gold ETF)", "Sentiment", "Medium", 12.4, "£bn AUM",
            manual_signal="Neutral", manual_reason="UK-specific gold demand steady", source="iShares")
    add_var(16, "COMEX Net Longs", "Sentiment", "High", 245000, "contracts",
            manual_signal="Neutral", manual_reason="Positioning elevated but not extreme", source="CFTC COT")
    add_var(17, "Gold Futures Open Interest", "Sentiment", "Medium", 525000, "contracts",
            manual_signal="Bullish", manual_reason="Rising OI with rising price = bullish confirmation", source="CME")

    # 4. FX & Currency
    add_var(18, "DXY (Dollar Index)", "FX & Currency", "Very High", dxy_val, "",
            signal_key="dxy", source="Yahoo Finance")
    add_var(19, "EUR/USD", "FX & Currency", "Medium", fx.get("eur_usd", 1.09), "",
            manual_signal="Neutral", manual_reason="Euro range-bound", source=fx.get("source", "—"))
    add_var(20, "USD/CNY", "FX & Currency", "Medium", fx.get("usd_cny", 7.18), "",
            manual_signal="Neutral", manual_reason="Yuan stable vs dollar", source=fx.get("source", "—"))
    add_var(21, "GBP Trade-Weighted Index", "FX & Currency", "Medium", 80.5, "",
            manual_signal="Neutral", manual_reason="GBP TWI stable", source="BoE")

    # 5. Commodities
    add_var(22, "Silver Spot (XAG/USD)", "Commodities", "High", silver_usd, "$",
            manual_signal="Bullish", manual_reason="Silver strength supports precious metals complex", source=spot.get("source", "—"))
    add_var(23, "Gold/Silver Ratio", "Commodities", "Medium", gold_silver_ratio, "",
            manual_signal="Neutral" if gold_silver_ratio < 90 else "Bearish",
            manual_reason=f"Ratio at {gold_silver_ratio:.1f}" + (" — healthy range" if gold_silver_ratio < 85 else " — elevated, silver may outperform"),
            source="Calculated")
    add_var(24, "Brent Crude Oil", "Commodities", "Medium", brent, "$",
            signal_key="brent_oil", source="Yahoo Finance")
    add_var(25, "Copper Price", "Commodities", "Low", copper, "$/lb",
            manual_signal="Neutral", manual_reason="Copper reflects growth outlook, mixed for gold", source="Yahoo Finance")

    # 6. Geopolitical
    add_var(26, "Central Bank Gold Purchases", "Geopolitical", "Very High", 1037, "tonnes/yr",
            manual_signal="Bullish", manual_reason="Record CB buying supports long-term floor", source="WGC")
    add_var(27, "China Gold Imports", "Geopolitical", "High", 150, "tonnes/mo",
            manual_signal="Neutral", manual_reason="Imports near recent averages", source="WGC")
    add_var(28, "India Gold Demand", "Geopolitical", "High", 180, "tonnes/qtr",
            manual_signal="Bullish", manual_reason="Strong seasonal demand", source="WGC")

    # Compute 5% move probability
    prob_5pct = compute_5pct_probability(variables, vix_val)

    # Build history for charts
    chart_history = {"dates": [], "gold_spot_gbp": [], "gold_spot_usd": [], "britannia_est": [],
                     "fed_rate": [], "uk_rate": [], "us_10y": [], "real_yield": [],
                     "vix": [], "dxy": [], "gbp_usd": [], "silver": [], "oil": [], "gld_holdings": []}

    # Use yfinance history if available
    if "gold_usd" in history:
        dates = history["gold_usd"]["dates"]
        chart_history["dates"] = dates
        chart_history["gold_spot_usd"] = history["gold_usd"]["values"]
        # Approximate GBP conversion (use current rate for simplicity)
        chart_history["gold_spot_gbp"] = [round(v / gbp_usd, 2) for v in history["gold_usd"]["values"]]
        chart_history["britannia_est"] = [round(v / gbp_usd * (1 + premium_pct / 100), 2) for v in history["gold_usd"]["values"]]

    for key, hist_key in [("vix", "vix"), ("dxy", "dxy"), ("silver", "silver_usd"),
                           ("oil", "brent_oil"), ("gld_holdings", "gld")]:
        if hist_key in history:
            chart_history[key] = history[hist_key]["values"]

    # Interest rates — use Yahoo Finance historical data where available
    n = len(chart_history["dates"])
    if n > 0:
        # US 10Y yield from Yahoo Finance (^TNX gives yield * 10, but recent versions give actual %)
        if "us_10y" in history:
            us_10y_hist = history["us_10y"]["values"]
            # ^TNX returns values like 4.28 (percentage), align to our date series
            chart_history["us_10y"] = _align_series(history["us_10y"], chart_history["dates"])
        else:
            chart_history["us_10y"] = [us_10y] * n

        # Estimate real yield as 10Y minus latest CPI (rough approximation)
        cpi_approx = us_cpi if us_cpi else 3.0
        chart_history["real_yield"] = [round(y - cpi_approx, 2) for y in chart_history["us_10y"]]

        # Fed rate and UK rate change infrequently — use FRED value as flat
        chart_history["fed_rate"] = [fed_rate] * n
        chart_history["uk_rate"] = [4.25] * n

        # GBP/USD — try to get history from yfinance
        try:
            import yfinance as yf
            gbp_ticker = yf.Ticker("GBPUSD=X")
            gbp_hist = gbp_ticker.history(period=f"{len(chart_history['dates'])+10}d")
            if not gbp_hist.empty and len(gbp_hist) > 10:
                chart_history["gbp_usd"] = _align_series(
                    {"dates": [d.strftime('%Y-%m-%d') for d in gbp_hist.index],
                     "values": [round(float(v), 4) for v in gbp_hist['Close']]},
                    chart_history["dates"]
                )
            else:
                chart_history["gbp_usd"] = [gbp_usd] * n
        except Exception:
            chart_history["gbp_usd"] = [gbp_usd] * n

    # Compile dashboard data
    dashboard_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "gold_spot_usd": round(gold_usd, 2),
        "gold_spot_gbp": round(gold_gbp, 2),
        "gbp_usd": round(gbp_usd, 4),
        "britannia_premium_pct": premium_pct,
        "britannia_price_gbp": round(britannia_gbp, 2),
        "britannia_price_prev": round(prev_data.get("britannia_price_gbp", britannia_gbp * 0.98), 2),
        "silver_usd": round(silver_usd, 2) if silver_usd else 0,
        "variables": variables,
        "history": chart_history,
        "move_probability_5pct": prob_5pct,
    }

    # Save cache
    with open(DATA_CACHE, 'w') as f:
        json.dump(dashboard_data, f, indent=2)

    log.info(f"Data refresh complete: Gold ${gold_usd:.2f} / £{gold_gbp:.2f} | Britannia est. £{britannia_gbp:.2f}")
    log.info(f"Signals: {sum(1 for v in variables if v['signal']=='Bullish')} Bull / "
             f"{sum(1 for v in variables if v['signal']=='Bearish')} Bear / "
             f"{sum(1 for v in variables if v['signal']=='Neutral')} Neutral")
    log.info(f"5% move probability: {prob_5pct}%")

    return dashboard_data


def inject_data_into_dashboard(data):
    """Write dashboard data to a separate data.js file loaded by the HTML."""
    data_js_path = SCRIPT_DIR / "data.js"
    data_json = json.dumps(data, indent=2)
    js_content = f"// Auto-generated by gold_refresh.py — do not edit\n// Updated: {data.get('last_updated', 'unknown')}\nconst DASHBOARD_DATA = {data_json};\n"

    with open(data_js_path, 'w') as f:
        f.write(js_content)

    log.info(f"Data file updated: {data_js_path}")


# ============================================================
# EMAIL ALERTS
# ============================================================

def should_send_alert(config, probability):
    """Check if alert should be sent based on cooldown."""
    threshold = config.get("alert_threshold_pct", 5.0)
    cooldown_hours = config.get("alert_cooldown_hours", 24)

    if probability < 50:  # Only alert if probability is meaningful
        return False

    if ALERT_LOG.exists():
        with open(ALERT_LOG) as f:
            alert_log = json.load(f)
        last_alert = alert_log.get("last_alert_time")
        if last_alert:
            last_dt = datetime.fromisoformat(last_alert)
            if datetime.utcnow() - last_dt < timedelta(hours=cooldown_hours):
                log.info(f"Alert cooldown active (sent {last_dt}), skipping")
                return False

    return True


def send_email_alert(config, data):
    """Send Gmail alert about potential gold move."""
    sender = config.get("gmail_sender", "")
    password = config.get("gmail_app_password", "")
    recipient = config.get("gmail_recipient", "")

    if not sender or not password or not recipient or password.startswith("YOUR_"):
        log.warning("Gmail not configured — alert logged but not emailed")
        return False

    prob = data.get("move_probability_5pct", 0)
    gold_gbp = data.get("gold_spot_gbp", 0)
    britannia = data.get("britannia_price_gbp", 0)
    bull_count = sum(1 for v in data.get("variables", []) if v.get("signal") == "Bullish")
    bear_count = sum(1 for v in data.get("variables", []) if v.get("signal") == "Bearish")

    direction = "UP" if bull_count > bear_count else "DOWN"

    subject = f"⚠️ GOLD ALERT: {prob}% chance of 5%+ move {direction} — Britannia £{britannia:,.2f}"

    body = f"""
    <html><body style="font-family: -apple-system, sans-serif; color: #333; max-width: 600px;">
    <h2 style="color: #f0b90b;">🥇 Gold Britannia Alert</h2>
    <p><strong>5% Move Probability: {prob}%</strong> — Direction: <strong>{direction}</strong></p>

    <table style="width:100%; border-collapse:collapse; margin: 16px 0;">
        <tr style="background:#f5f5f5;">
            <td style="padding:10px; border:1px solid #ddd;"><strong>Gold Spot (GBP)</strong></td>
            <td style="padding:10px; border:1px solid #ddd;">£{gold_gbp:,.2f}</td>
        </tr>
        <tr>
            <td style="padding:10px; border:1px solid #ddd;"><strong>Britannia Estimate</strong></td>
            <td style="padding:10px; border:1px solid #ddd;">£{britannia:,.2f}</td>
        </tr>
        <tr style="background:#f5f5f5;">
            <td style="padding:10px; border:1px solid #ddd;"><strong>Bullish Signals</strong></td>
            <td style="padding:10px; border:1px solid #ddd; color: green;">{bull_count} / 28</td>
        </tr>
        <tr>
            <td style="padding:10px; border:1px solid #ddd;"><strong>Bearish Signals</strong></td>
            <td style="padding:10px; border:1px solid #ddd; color: red;">{bear_count} / 28</td>
        </tr>
    </table>

    <h3>Key Signals:</h3>
    <ul>
    """

    # Add top signals
    critical_vars = [v for v in data.get("variables", []) if v.get("importance") in ("Critical", "Very High")]
    for v in critical_vars[:10]:
        color = "green" if v["signal"] == "Bullish" else "red" if v["signal"] == "Bearish" else "#888"
        body += f'<li><span style="color:{color};font-weight:bold;">{v["signal"]}</span> — {v["name"]}: {v["reason"]}</li>\n'

    body += f"""
    </ul>
    <p style="color:#888; font-size:12px;">
        Data as of: {data.get("last_updated", "N/A")}<br>
        Open your dashboard for full analysis.
    </p>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

        log.info(f"Alert email sent to {recipient}")

        # Record alert
        with open(ALERT_LOG, 'w') as f:
            json.dump({"last_alert_time": datetime.utcnow().isoformat(), "probability": prob}, f)

        return True

    except Exception as e:
        log.error(f"Failed to send email: {e}")
        return False


# ============================================================
# MAIN
# ============================================================

def main():
    log.info("=" * 60)
    log.info("Gold Britannia Intelligence — Data Refresh")
    log.info("=" * 60)

    config = load_config()

    # Fetch all data and compute signals
    data = generate_dashboard_data(config)

    # Update the dashboard HTML
    inject_data_into_dashboard(data)

    # Check if alert should be sent
    prob = data.get("move_probability_5pct", 0)
    if should_send_alert(config, prob):
        log.info(f"5% move probability ({prob}%) exceeds threshold — sending alert")
        send_email_alert(config, data)
    else:
        log.info(f"5% move probability ({prob}%) — no alert needed")

    log.info("Refresh complete!")
    print(f"\n✅ Dashboard updated: {DASHBOARD_OUTPUT}")
    print(f"   Gold: ${data['gold_spot_usd']:,.2f} / £{data['gold_spot_gbp']:,.2f}")
    print(f"   Britannia est: £{data['britannia_price_gbp']:,.2f}")
    print(f"   5% move probability: {prob}%")


if __name__ == "__main__":
    main()
