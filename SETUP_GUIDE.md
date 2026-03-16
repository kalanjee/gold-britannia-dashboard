# Gold Britannia Intelligence Dashboard — Setup Guide

## Quick Start (15 minutes)

### Step 1: Install Python dependencies
```bash
pip install requests yfinance pandas
```

### Step 2: Get your free API keys

**FRED API (US macro data — essential)**
1. Go to https://fred.stlouisfed.org/docs/api/api_key.html
2. Create a free account
3. Request an API key (instant approval)
4. Copy your key

**Open Exchange Rates (FX data)**
1. Go to https://openexchangerates.org/signup/free
2. Sign up for the free "Forever Free" plan (300 requests/month = ~10/day)
3. Copy your App ID from the dashboard

### Step 3: Set up Gmail App Password (for alerts)
1. Go to https://myaccount.google.com/apppasswords
2. You need 2-Factor Authentication enabled on your Google account
3. Select "Mail" and "Other (Custom name)" → name it "Gold Dashboard"
4. Google generates a 16-character password — copy it
5. This password lets the script send emails through your Gmail

### Step 4: Run for the first time
```bash
cd /path/to/your/Investments/folder
python gold_refresh.py
```
This creates `config.json`. Edit it with your keys:
```json
{
  "fred_api_key": "paste_your_fred_key_here",
  "open_exchange_rates_key": "paste_your_oer_app_id_here",
  "gmail_sender": "your.email@gmail.com",
  "gmail_app_password": "paste_16char_app_password",
  "gmail_recipient": "kalanjee@gmail.com",
  "alert_threshold_pct": 5.0,
  "alert_cooldown_hours": 24,
  "britannia_premium_pct": 3.8
}
```

### Step 5: Run again to fetch live data
```bash
python gold_refresh.py
```
Then open `gold_britannia_dashboard.html` in your browser.

---

## Scheduling Automatic Refreshes

### macOS / Linux (cron)
```bash
# Edit your crontab
crontab -e

# Add this line to refresh every 4 hours:
0 */4 * * * cd /path/to/Investments && python3 gold_refresh.py >> /tmp/gold_refresh.log 2>&1

# Or every hour during UK market hours (8am-6pm):
0 8-18 * * 1-5 cd /path/to/Investments && python3 gold_refresh.py
```

### Windows (Task Scheduler)
1. Open Task Scheduler → Create Basic Task
2. Name: "Gold Dashboard Refresh"
3. Trigger: Daily, repeat every 4 hours
4. Action: Start a program
   - Program: `python`
   - Arguments: `gold_refresh.py`
   - Start in: `C:\path\to\Investments`

---

## All 28 Variables & Their Data Sources

### FREE APIs (automated, no cost)

| # | Variable | Source | URL | Update Freq |
|---|----------|--------|-----|-------------|
| 1 | Gold Spot (XAU/USD) | Metals.live | api.metals.live/v1/spot | Real-time |
| 2 | GBP/USD Rate | Open Exchange Rates | openexchangerates.org | Hourly |
| 3 | Silver Spot (XAG/USD) | Metals.live | api.metals.live/v1/spot | Real-time |
| 5 | US Fed Funds Rate | FRED | api.stlouisfed.org | Monthly |
| 7 | US CPI (YoY) | FRED | api.stlouisfed.org | Monthly |
| 9 | US 10Y Treasury Yield | FRED | api.stlouisfed.org | Daily |
| 11 | US Real Yield (TIPS) | FRED | api.stlouisfed.org | Daily |
| 12 | US M2 Money Supply | FRED | api.stlouisfed.org | Monthly |
| 13 | VIX (Fear Index) | Yahoo Finance | via yfinance lib | Real-time |
| 14 | GLD ETF Holdings | Yahoo Finance | via yfinance lib | Daily |
| 18 | DXY (Dollar Index) | Yahoo Finance | via yfinance lib | Real-time |
| 19 | EUR/USD | Open Exchange Rates | openexchangerates.org | Hourly |
| 20 | USD/CNY | Open Exchange Rates | openexchangerates.org | Hourly |
| 22 | Silver Spot | Metals.live | api.metals.live/v1/spot | Real-time |
| 24 | Brent Crude Oil | Yahoo Finance | via yfinance lib | Real-time |
| 25 | Copper Price | Yahoo Finance | via yfinance lib | Real-time |

### SEMI-AUTOMATIC (free but requires periodic manual input)

| # | Variable | Source | How to Update |
|---|----------|--------|---------------|
| 3 | Britannia Premium | Dealer websites | Check BullionByPost/Chards weekly, update config.json |
| 4 | UK VAT Status | HMRC | Check quarterly — Britannias are VAT-free |
| 6 | UK Bank Rate | Bank of England | Updated on BoE decision days (monthly) |
| 8 | UK CPI (YoY) | ONS | Published monthly by Office for National Statistics |
| 10 | UK 10Y Gilt Yield | Bank of England | BoE statistical database |
| 15 | SGLN (UK Gold ETF) | iShares | Check iShares.com monthly |
| 16 | COMEX Net Longs | CFTC | Weekly COT report (Fridays) at cftc.gov |
| 17 | Gold Futures OI | CME Group | cmegroup.com daily |
| 21 | GBP Trade-Weighted | Bank of England | BoE statistical database |
| 26 | CB Gold Purchases | World Gold Council | gold.org quarterly reports |
| 27 | China Gold Imports | World Gold Council | gold.org monthly/quarterly |
| 28 | India Gold Demand | World Gold Council | gold.org quarterly |

---

## The Britannia Premium Problem (and solutions)

UK gold dealers (BullionByPost, Chards, Atkinsons, Royal Mint) use aggressive anti-scraping:
- JavaScript-rendered prices (no static HTML)
- CloudFlare / Akamai bot protection
- CAPTCHAs on repeated visits
- Dynamic pricing that changes every few minutes

### Solution 1: Manual Weekly Check (Recommended — Free)
Every Sunday, spend 5 minutes checking these 4 sites and update config.json:
- BullionByPost: bullionbypost.co.uk/gold-coins/britannia
- Chards: chards.co.uk
- Atkinsons: atkinsonsbullion.com
- Royal Mint: royalmint.com

### Solution 2: Price Alert Services (Free)
- **BullionByPost** has email price alerts — sign up at their site
- **Gold.co.uk** aggregates dealer prices and offers email alerts
- Set alerts for your target buy/sell prices

### Solution 3: Automated Scraping (£20-40/month)
If you want fully automated dealer prices:
- **Apify.com** (cloud scraping): £30/month for scheduled scraping runs
- **ScrapingBee.com**: £25/month, handles JavaScript rendering
- **Puppeteer + residential proxy**: DIY option, needs a VPS

### Solution 4: GoldAPI.io (£15/month)
- Provides gold spot prices in GBP with dealer markup data
- REST API, easy to integrate
- URL: goldapi.io

---

## Important Notes

### Gold Britannia Tax Status (UK)
- **VAT**: Gold Britannias are **VAT-FREE** as UK legal tender gold coins
- **CGT**: Gold Britannias are **CGT-EXEMPT** as UK legal tender
- This makes them one of the most tax-efficient ways to hold physical gold in the UK
- The dashboard reflects this — no VAT is added to the price estimate

### How the 5% Move Probability Works
The model combines three factors:
1. **VIX level** — higher fear = higher probability of large moves
2. **Signal concentration** — if most variables point the same direction, momentum builds
3. **Weighted signal score** — Critical/Very High variables weighted more heavily

When probability exceeds 50%, an email alert is sent (respecting the 24hr cooldown).

### Data Quality Hierarchy
For the most reliable analysis, prioritise:
1. **FRED** — Official US Federal Reserve data, highly reliable
2. **Metals.live** — Real-time precious metals, good uptime
3. **Yahoo Finance** — Comprehensive but occasionally unreliable
4. **Open Exchange Rates** — Good free tier, official exchange rates
5. **Manual sources** — WGC, BoE, ONS — most authoritative but requires manual entry

---

## Troubleshooting

**"yfinance not found"**
```bash
pip install yfinance --break-system-packages
```

**"FRED API key not configured"**
Edit config.json and add your FRED key. Get one free at fred.stlouisfed.org.

**"Email alert failed"**
- Check your Gmail App Password is correct (16 characters, no spaces)
- Ensure 2FA is enabled on your Google account
- Try sending a test email manually first

**Dashboard shows sample data**
Run `python gold_refresh.py` to inject live data into the HTML file.

**Metals.live API returning errors**
The API has rate limits. If you're hitting them, reduce refresh frequency or add yfinance as primary source instead.
