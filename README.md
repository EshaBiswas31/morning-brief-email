# ☀️ Morning Brief

A pre-market brief for Indian and global markets, emailed to you every weekday morning.
It tells you **what happened**, and also **what it likely means next**: forward-looking odds with the reasoning behind them, and a running score of how accurate past calls were.

**Collect → Compute → Summarize → Format → Deliver → Schedule**

- **Prices:** Yahoo Finance (`yfinance`): indices, macro, and your watchlist
- **Signals:** computed in Python (RSI, 50-day average crosses, 52-week highs/lows, volume spikes, big moves)
- **News:** public RSS feeds, deduplicated
- **Outlook (forward-looking):** historical base rates: "the last time the chart looked like this, what happened next?" (details below)
- **Scorecard:** every call is logged and graded once its time is up, so you can see the real hit rate
- **Summary (optional):** Claude writes the narrative from the data. It never invents numbers: the price table is built by code, and the prompt forbids using anything outside the data.
- **Delivery:** email through Gmail. Every brief is also shown on the GitHub Actions run page.
- **Schedule:** GitHub Actions, about 8 AM IST, Monday to Friday (free)

No Anthropic key? The brief still goes out with prices, signals and headlines, just without the AI summary. If one news feed breaks, it is skipped.

---

## Project layout

```
config.yaml          ← edit this: delivery method, tickers, watchlist, feeds, thresholds, model
main.py              ← runs the whole pipeline
brief/
  market.py          ← downloads prices (one batch per group)
  indicators.py      ← RSI, moving averages, signals (pure pandas)
  outlook.py         ← forward-looking odds from historical base rates
  scorecard.py       ← logs predictions and grades them later
  news.py            ← RSS fetching + duplicate removal
  summarize.py       ← the Claude prompt and API call
  report.py          ← formats the final message
  deliver.py         ← email, Telegram (optional), GitHub run page, saved copy
data/predictions.csv ← every call and its outcome (created and updated automatically)
tests/               ← tests for the logic (run automatically before each brief)
.github/workflows/   ← the daily schedule
```

---

## How the outlook works

For each index and watchlist stock, the code describes today's chart with three labels:

| Label | Values |
|---|---|
| **Trend** | uptrend (above 50-DMA, 50-DMA above 200-DMA), downtrend, or mixed |
| **RSI zone** | oversold, weak, neutral, strong, overbought |
| **Yesterday's move** | sharp drop, down, flat, up, sharp rise (compared with that stock's normal daily move) |

It then finds every day in the last 5 years with the same labels and measures how often the price was higher **5 sessions later**. If there are fewer than 30 matches, it drops a label and tries again.

- **Bias** is bullish or bearish only when the odds are clearly different from normal (at least 55% or at most 45%, and 5+ percentage points away from that stock's normal rate). Otherwise it says "no clear edge".
- **Confidence** is "low" or "moderate", never "high". Markets are noisy, and overlapping 5-day windows make the sample look bigger than it is.
- **Wrong if** gives a price level (the 10-day high or low) that would invalidate the view.

**Overnight US cue:** US markets close after Indian markets, so last night's S&P 500 move is new information for today's Nifty. The brief shows how Nifty historically did the day after a similar S&P move.

**Scorecard:** each run grades calls whose 5 sessions have passed (hit or miss) and adds today's calls to `data/predictions.csv`. GitHub saves that file back to the repository automatically. The brief shows the hit rate over the last 60 days. Expect something in the 50–60% range; that is what a real edge looks like in markets. Anything much higher on a small sample is probably luck.

**Limits, stated honestly:** base rates describe the past and assume the future rhymes with it. They ignore news, earnings and events unless you add them. Treat the outlook as one input for your own judgement, not a trading signal.

---

## Setup (about 15 minutes)

### 1. Create a Gmail app password
Gmail doesn't let programs use your normal password. You create a separate 16-letter "app password" instead.

1. Turn on **2-Step Verification** for your Google account (required for app passwords): [myaccount.google.com/security](https://myaccount.google.com/security).
2. Open [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Type a name such as "Morning Brief" and click **Create**.
4. Copy the 16-letter password it shows. It is shown only once.

This password only allows sending and reading mail through apps. You can delete it anytime from the same page.

### 2. Add secrets to GitHub
In your repository: **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Name | Value | Needed? |
|---|---|---|
| `EMAIL_ADDRESS` | your Gmail address | Yes |
| `EMAIL_APP_PASSWORD` | the 16-letter app password | Yes |
| `EMAIL_TO` | a different address to receive the brief (comma-separated for several) | Optional: defaults to `EMAIL_ADDRESS` |
| `ANTHROPIC_API_KEY` | key from [console.anthropic.com](https://console.anthropic.com) | Optional: adds the AI summary (paid, under a cent per brief with Haiku) |

### 3. Run it
Go to the **Actions** tab → **Morning Brief** → **Run workflow**. Within a couple of minutes the brief lands in your inbox (check Spam the first time and mark it "Not spam").

You can also read every brief on GitHub: click a run in the **Actions** tab and scroll down to the summary.

After that it runs automatically every weekday.

> GitHub pauses scheduled workflows in repositories with no activity for 60 days. If the brief stops, push any small commit or re-enable it in the Actions tab.

### Run it on your own computer (optional)
```bash
python -m venv .venv
.venv\Scripts\activate             # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # Mac/Linux: cp; then fill in your values
pytest -q                          # all tests should pass
python main.py --dry-run --no-ai   # data only, printed to screen
python main.py --dry-run           # with Claude summary (needs key), printed
python main.py                     # sends the email
```

---

## Customizing

- **Delivery method:** in `config.yaml`, set `delivery: method:` to `email`, `telegram` or `none` (`none` = read it only on the GitHub run page).
- **Watchlist:** edit `watchlist:` in `config.yaml`. NSE stocks end in `.NS`, BSE in `.BO`. Search the symbol on finance.yahoo.com if unsure.
- **What counts as "notable":** change the thresholds under `signals:`.
- **Outlook:** under `outlook:` change the horizon (`horizon_days`), history length (`lookback`), which indices are scored, or turn it off (`enabled: false`).
- **News sources:** add or remove RSS URLs under `news: feeds:`.
- **Tone and structure:** edit `SYSTEM_PROMPT` in `brief/summarize.py`. This is where most quality improvements come from.
- **Model:** change `claude: model:` to `claude-sonnet-5` for deeper analysis (more expensive).
- **Time:** edit the cron line in `.github/workflows/morning-brief.yml`. It's in UTC: IST minus 5:30.

## Known limitations

- Yahoo Finance data is unofficial and sometimes delayed or briefly unavailable.
- RSS feed URLs change occasionally. The brief notes how many feeds failed.
- On Indian market holidays the Indian indices show their last trading date.
- This is an information tool, not investment advice.

## Ideas for next versions

1. Add more evidence to the outlook: sector strength, FII/DII flows, earnings dates, India VIX regime
2. Replace the rule-based setups with a trained model (e.g. gradient boosting) validated with walk-forward testing
3. Market-wide "top movers" scan across all Nifty 50 stocks
4. A nicer HTML email with charts
5. A Streamlit dashboard showing the scorecard and past briefs
