# Robinhood Advisor - Setup Guide

**Goal:** Get your portfolio advisor running in 30 minutes

---

## Step 1: Install Dependencies (10 minutes)

```bash
cd /workspace/group/robinhood-advisor
pip install -r requirements.txt
```

**What gets installed:**
- `robin-stocks` - Robinhood API access
- `yfinance` - Free stock data (no API key needed)
- `pandas` - Data analysis
- `flask` - Web GUI (later)
- `schedule` - Daily automation

---

## Step 2: Configure (5 minutes)

### Option A: Test with Mock Data (Recommended First)

No configuration needed! Just run:
```bash
python advisor.py
```

This will analyze 5 sample stocks (AAPL, NVDA, TSLA, MSFT, GOOGL) and show you what the output looks like.

### Option B: Connect Real Robinhood Account

Create `.env` file:
```bash
touch .env
```

Add your credentials:
```
ROBINHOOD_USERNAME=your_email@gmail.com
ROBINHOOD_PASSWORD=your_password
```

**If you have 2-factor authentication:**
```
ROBINHOOD_MFA_CODE=123456
```

**Note:** The MFA code changes every 30 seconds. You'll need to update it each time you run the script (or we can set up automated token refresh later).

---

## Step 3: Test the System (15 minutes)

### Test 1: Individual Components

```bash
# Test sentiment analysis
python sentiment_engine.py

# Test technical analysis
python quant_engine.py

# Test recommendation engine
python recommendation_engine.py
```

Each test should print results and complete without errors.

### Test 2: Full Analysis (Mock Data)

```bash
python advisor.py
```

**What you should see:**
1. "Starting daily analysis..."
2. Analysis of 5 stocks
3. Recommendations generated
4. Email-formatted report printed
5. "Analysis complete!"

**Expected output:**
```
═══════════════════════════════════════════════
  PORTFOLIO MORNING BRIEF
  February 26, 2026
═══════════════════════════════════════════════

Portfolio Value: $4,500.00
Positions: 5

═══════════════════════════════════════════════
  🎯 TODAY'S RECOMMENDATIONS (2 orders)
═══════════════════════════════════════════════

🟢 1. AAPL - BUY
   Current: $175.20
   → Limit BUY: $174.50 (5 shares)
   ...
```

### Test 3: With Real Portfolio (Optional)

```bash
python advisor.py --use-robinhood
```

This will:
1. Login to Robinhood
2. Fetch your actual 20 stocks
3. Analyze each one
4. Generate personalized recommendations

---

## Step 4: Schedule Daily Automation

### Option A: Using Nanoclaw Scheduler (Recommended)

Since you already have nanoclaw running, we'll integrate with that.

**Create scheduled task:**

```python
# In your main nanoclaw group
from mcp__nanoclaw__schedule_task import schedule_task

schedule_task(
    prompt="Run Robinhood daily analysis and email results to kevinclaw26@gmail.com",
    schedule_type="cron",
    schedule_value="0 8 * * *",  # Every day at 8 AM
    context_mode="isolated"  # Fresh session each time
)
```

**Or manually add to cron:**
```bash
crontab -e
```

Add this line:
```
0 8 * * * cd /workspace/group/robinhood-advisor && python schedule_daily.py
```

### Option B: Run Manually Each Morning

Just run this command each morning:
```bash
cd /workspace/group/robinhood-advisor
python schedule_daily.py
```

The output will be your daily report. Copy it to email or set up email forwarding.

---

## Step 5: First Morning Usage

**8:00 AM** - System runs automatically (or you run it manually)

**8:01 AM** - Check your email or the terminal output

**8:05 AM** - Review recommendations:
- Do the stocks make sense?
- Are the signals strong?
- Do you agree with the sentiment?

**8:10 AM** - Place limit orders in Robinhood app:
1. Open Robinhood app
2. Find the stock (e.g., AAPL)
3. Tap "Trade"
4. Select "Buy" or "Sell"
5. Change "Market Order" to "Limit Order"
6. Enter the exact limit price from the email
7. Enter the number of shares
8. Set "Good for Day"
9. Review and submit

**Rest of Day** - Orders execute automatically if price reaches your limit

**End of Day** - Check which orders filled

---

## Configuration Options

Edit `config.py` to customize:

### Change Daily Trade Limit
```python
MAX_DAILY_TRADES = 3  # Change to 1-5
```

### Adjust Signal Sensitivity
```python
MIN_SIGNAL_STRENGTH = 0.65  # Lower for more recommendations (0.6)
                             # Higher for fewer (0.75)
```

### Change Email Time
```python
EMAIL_TIME = "08:00"  # Change to "07:00" or "09:00"
```

### Adjust Position Sizing
```python
MAX_POSITION_SIZE = 0.08  # 8% - change to 0.05 for smaller positions
```

---

## Troubleshooting

### Issue: "Module not found"
**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: Robinhood login fails
**Solutions:**
1. Check username/password in .env
2. If using 2FA, set ROBINHOOD_MFA_CODE
3. Try logging in via Robinhood app first (sometimes triggers unlock)
4. Use mock data mode for testing: `python advisor.py`

### Issue: No recommendations generated
**This is normal!** The system is conservative and only recommends when:
- Signal strength ≥ 65%
- At least 2 news articles available
- Technical indicators align

**If you want more recommendations:**
1. Lower MIN_SIGNAL_STRENGTH to 0.60 in config.py
2. Lower MIN_EDGE_REQUIRED to 0.02

### Issue: yfinance data errors
**Solution:** Yahoo Finance sometimes has issues. Just retry in a few minutes.

### Issue: Analysis takes too long
**Solution:** System analyzes all 20 stocks sequentially. Takes 2-3 minutes total. This is normal.

---

## Understanding the Recommendations

### Signal Strength Meaning

- **0.80-1.00 (Strong Buy)** - All indicators bullish, high confidence
- **0.65-0.79 (Buy)** - Most indicators bullish, good entry point
- **0.45-0.64 (Hold)** - Mixed signals, keep current position
- **0.35-0.44 (Sell)** - Most indicators bearish, consider exit
- **0.00-0.34 (Strong Sell)** - All indicators bearish, exit position

### Limit Price Logic

**Buy orders:** Set 0.5% below current price
- Current: $100 → Limit: $99.50
- Reason: Wait for small dip before entering

**Sell orders:** Set 0.5% above current price
- Current: $100 → Limit: $100.50
- Reason: Wait for small bounce before exiting

**Why limit orders?**
- Never overpay (buys)
- Never undersell (sells)
- Orders execute automatically when price is good
- If price never reaches limit, order expires (which is fine!)

---

## Data Storage

All data saved in `data/` folder:

- `analysis_YYYYMMDD.json` - Full analysis results
- `daily_report_YYYYMMDD.txt` - Email text reports
- `portfolio.json` - Current positions snapshot
- `trade_history.json` - Track recommendations over time
- `performance.json` - Weekly/monthly performance

Keep this folder backed up to track your strategy performance.

---

## Performance Tracking

Coming in Phase 2:
```bash
python analyzer.py --performance
```

Will show:
- Total recommendations given
- How many you followed
- Win rate on followed recommendations
- Average return per trade
- Strategy performance vs. SPY benchmark

---

## Next Features to Build

**Week 1:** Use as-is with terminal output
**Week 2:** Integrate with nanoclaw scheduler for emails
**Week 3:** Add performance tracking
**Week 4:** Build web GUI dashboard

Each week is an incremental improvement while you're actively using it.

---

## Quick Command Reference

```bash
# Test with mock data
python advisor.py

# Test with real portfolio
python advisor.py --use-robinhood

# Run daily report (for scheduler)
python schedule_daily.py

# Test individual components
python sentiment_engine.py
python quant_engine.py
python recommendation_engine.py
python portfolio_analyzer.py
```

---

## Security Notes

**Your Robinhood credentials:**
- Stored in `.env` file (never committed to git)
- Only used to fetch portfolio data
- Add `.env` to `.gitignore`

**API keys:**
- Not required for basic version
- News API optional (system works without it)
- All market data from free yfinance

---

**You're ready to go! Start with mock data testing, then connect your real portfolio when comfortable.**

Questions? Check the main README.md or config.py comments.

🎯 Let's build wealth systematically!
