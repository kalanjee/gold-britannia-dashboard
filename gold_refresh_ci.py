#!/usr/bin/env python3
"""
Gold Britannia — CI/GitHub Actions Refresh Script
===================================================
Identical to gold_refresh.py but reads API keys from environment
variables (GitHub Secrets) instead of config.json.

Environment variables expected:
  FRED_API_KEY, OER_API_KEY, GMAIL_SENDER, GMAIL_APP_PASSWORD, GMAIL_RECIPIENT
"""

import json
import os
import sys
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# Re-use all the core logic from gold_refresh.py
# We import the module directly
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from gold_refresh import (
    fetch_gold_spot, fetch_fx_rates, fetch_fred_series, fetch_macro_data,
    fetch_market_data, fetch_historical, compute_signal, compute_5pct_probability,
    generate_dashboard_data, inject_data_into_dashboard,
    should_send_alert, send_email_alert,
    DATA_CACHE, DASHBOARD_OUTPUT, ALERT_LOG, log
)

def build_config_from_env():
    """Build config dict from environment variables (GitHub Secrets)."""
    return {
        "fred_api_key": os.environ.get("FRED_API_KEY", ""),
        "open_exchange_rates_key": os.environ.get("OER_API_KEY", ""),
        "gmail_sender": os.environ.get("GMAIL_SENDER", ""),
        "gmail_app_password": os.environ.get("GMAIL_APP_PASSWORD", ""),
        "gmail_recipient": os.environ.get("GMAIL_RECIPIENT", "kalanjee@gmail.com"),
        "alert_threshold_pct": 5.0,
        "alert_cooldown_hours": 24,
        "britannia_premium_pct": float(os.environ.get("BRITANNIA_PREMIUM_PCT", "3.8")),
    }


def main():
    log.info("=" * 60)
    log.info("Gold Britannia Intelligence — CI Refresh (GitHub Actions)")
    log.info("=" * 60)

    config = build_config_from_env()

    # Check we have at least one key
    has_fred = config["fred_api_key"] and not config["fred_api_key"].startswith("YOUR_")
    has_oer = config["open_exchange_rates_key"] and not config["open_exchange_rates_key"].startswith("YOUR_")
    log.info(f"FRED key: {'configured' if has_fred else 'MISSING'}")
    log.info(f"OER key: {'configured' if has_oer else 'MISSING'}")

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

    log.info("CI refresh complete!")
    print(f"\n✅ Dashboard updated")
    print(f"   Gold: ${data['gold_spot_usd']:,.2f} / £{data['gold_spot_gbp']:,.2f}")
    print(f"   Britannia est: £{data['britannia_price_gbp']:,.2f}")
    print(f"   5% move probability: {prob}%")


if __name__ == "__main__":
    main()
