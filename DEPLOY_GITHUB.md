# Deploy Gold Britannia Dashboard to GitHub Pages

## Step-by-step (about 15 minutes)

### 1. Create a private GitHub repo

Go to https://github.com/new and create a repo:
- Name: `gold-britannia-dashboard` (or whatever you like)
- **Private** (your API data stays hidden; GitHub Pages works on private repos with a free account)
- Don't initialise with README

### 2. Push your files

Open a terminal in your Investments folder and run:

```bash
cd /path/to/your/Investments

git init
git add gold_britannia_dashboard.html gold_refresh.py gold_refresh_ci.py requirements.txt .gitignore .github/ SETUP_GUIDE.md DEPLOY_GITHUB.md
git commit -m "Initial commit — Gold Britannia Dashboard"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/gold-britannia-dashboard.git
git push -u origin main
```

### 3. Add your API keys as GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

Add these secrets (one at a time):

| Secret name        | Value                                      |
|--------------------|--------------------------------------------|
| `FRED_API_KEY`     | Your FRED API key                          |
| `OER_API_KEY`      | Your Open Exchange Rates App ID            |
| `GMAIL_SENDER`     | Your Gmail address                         |
| `GMAIL_APP_PASSWORD` | Your 16-character Gmail App Password     |
| `GMAIL_RECIPIENT`  | `kalanjee@gmail.com` (or wherever you want alerts) |

### 4. Enable GitHub Pages

Go to your repo → Settings → Pages:
- Source: **Deploy from a branch**
- Branch: `main`
- Folder: `/ (root)`
- Click Save

After a minute or two, your dashboard will be live at:
```
https://YOUR_USERNAME.github.io/gold-britannia-dashboard/gold_britannia_dashboard.html
```

### 5. Test the auto-refresh

Go to your repo → Actions → "Refresh Gold Dashboard" → Run workflow (manual trigger).

Watch it run. It should:
1. Fetch live data from all APIs
2. Update the dashboard HTML
3. Commit and push the changes
4. Send you an email if the 5% probability threshold is met

From now on, this runs automatically every 4 hours.

---

## How it works

```
Every 4 hours (cron):
  GitHub Actions runner spins up
    → Installs Python + dependencies
    → Runs gold_refresh_ci.py
       → Fetches gold spot from Metals.live
       → Fetches FX from Open Exchange Rates
       → Fetches macro data from FRED
       → Fetches VIX, DXY, oil, etc. from Yahoo Finance
       → Computes 28 variable signals
       → Calculates 5% move probability
       → If probability > 50%: sends Gmail alert
       → Injects live data into dashboard HTML
    → Commits updated HTML back to repo
    → GitHub Pages serves the new version
```

---

## Keeping it private

With a **private repo**, only you can see the dashboard. GitHub Pages on private repos is available on the free plan for personal accounts.

If you ever want to add a collaborator, go to Settings → Collaborators.

---

## Changing the refresh schedule

Edit `.github/workflows/refresh-dashboard.yml` and change the cron line:

```yaml
# Every 2 hours:
- cron: '0 */2 * * *'

# Every hour during UK market hours (8am-6pm UTC):
- cron: '0 8-18 * * 1-5'

# Every 30 minutes:
- cron: '*/30 * * * *'
```

Note: GitHub Actions free tier gives you 2,000 minutes/month. Each refresh takes about 1-2 minutes, so even running every hour you'd only use ~720 minutes.

---

## Updating the Britannia premium

Since dealer prices can't be easily automated, you can update the premium in two ways:

**Option A: Edit the GitHub Secret**
Add a secret called `BRITANNIA_PREMIUM_PCT` with the current premium percentage (e.g. `4.2`).

**Option B: Edit config.json locally**
Update `britannia_premium_pct` in your local config.json and run `python gold_refresh.py` manually.

---

## Troubleshooting

**Actions workflow failed:**
Check the Actions tab → click the failed run → read the logs. Common issues:
- Missing secrets (double-check the names match exactly)
- yfinance rate-limited (rare, just re-run)

**Dashboard not updating on GitHub Pages:**
GitHub Pages can take 1-2 minutes to update. Hard-refresh your browser (Ctrl+Shift+R).

**Email alerts not sending:**
- Check GMAIL_SENDER and GMAIL_APP_PASSWORD secrets
- Make sure 2FA is enabled on your Google account
- Check the Actions log for the specific error message
