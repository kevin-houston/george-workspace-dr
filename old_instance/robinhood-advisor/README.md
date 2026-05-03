# Robinhood Portfolio Advisor

**Automated daily portfolio analysis with limit order recommendations**

Customized for:
- 20 stock portfolio (~$4,500)
- Swing trading (not day trading)
- Daily email reports at 8 AM
- Local GUI dashboard

---

## What This Does

Every morning at 8 AM, you get an email with:

1. **Portfolio Summary** - Current value, returns, positions
2. **Buy Recommendations** - Stocks showing strong signals with specific limit prices
3. **Sell Recommendations** - Positions to trim or exit
4. **Hold List** - Positions that look good to keep

**Example Morning Email:**
```
📊 PORTFOLIO MORNING BRIEF - February 27, 2026

Portfolio Value: $4,650.00 (+2.3% total return)
Positions: 20

═══════════════════════════════════════════════

🎯 TODAY'S RECOMMENDATIONS (3 orders)

🟢 1. AAPL - BUY
   Current: $175.20
   → Limit BUY: $174.50 (5 shares)
   Order Value: $872.50
   Signal: 78%
   Rationale: Sentiment: BULLISH, Technical: BUY, RSI oversold (32)

🔴 2. TSLA - SELL
   Current: $238.00
   → Limit SELL: $238.50 (3 shares)
   Order Value: $715.50
   Signal: 28%
   Rationale: Sentiment: BEARISH, Technical: SELL

═══════════════════════════════════════════════
```

---

## Quick Start

### 1. Install Dependencies (5 minutes)

```bash
cd /workspace/group/robinhood-advisor
pip install -r requirements.txt
```

### 2. Configure Robinhood Login

Create `.env` file:
```bash
ROBINHOOD_USERNAME=your_email@gmail.com
ROBINHOOD_PASSWORD=your_password
# ROBINHOOD_MFA_CODE=123456  # If using 2FA
```

### 3. Test the System

```bash
# Test with mock data (no login required)
python advisor.py

# Test with real portfolio
python advisor.py --use-robinhood
```

### 4. Schedule Daily Reports

The advisor will integrate with your nanoclaw scheduler:
```bash
# Run every morning at 8 AM
python advisor.py --schedule
```

---

## How It Works

### Analysis Pipeline

```
1. Connect to Robinhood → Fetch your 20 stocks
2. For each stock:
   ├─ Fetch news headlines (last 3 days)
   ├─ Analyze sentiment (bullish/bearish)
   ├─ Fetch price data (6 months)
   ├─ Calculate technical indicators (RSI, MACD, MAs)
   └─ Combine signals → Generate recommendation
3. Filter to top 3 actionable trades
4. Format email report
5. Send to kevinclaw26@gmail.com
```

### Signal Combination

**Sentiment Analysis (40% weight):**
- News headline analysis
- Positive/negative word counting
- Confidence based on article count

**Technical Analysis (60% weight):**
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- 50-day and 200-day moving averages
- Volume trends
- Support/resistance levels

**Combined Signal:** 0.0 (strong sell) to 1.0 (strong buy)

### Thresholds

- **Strong Buy:** Signal ≥ 0.80
- **Buy:** Signal ≥ 0.65
- **Hold:** Signal 0.45 - 0.65
- **Sell:** Signal ≤ 0.35
- **Strong Sell:** Signal ≤ 0.20

---

## Configuration

Edit `config.py` to customize:

```python
# Portfolio Settings
PORTFOLIO_SIZE = 4500
NUM_HOLDINGS = 20

# Strategy
STRATEGY_TYPE = "swing"  # Not day trading
MIN_HOLD_DAYS = 2
TARGET_RETURN_PER_TRADE = 0.05  # 5%
MAX_LOSS_PER_TRADE = 0.03  # 3%

# Daily Limits
MAX_DAILY_TRADES = 3  # Max recommendations per day
MIN_SIGNAL_STRENGTH = 0.65  # Only strong signals

# Risk Management
MAX_POSITION_SIZE = 0.08  # 8% max in any stock
CASH_RESERVE = 0.05  # Keep 5% cash

# Email
EMAIL_RECIPIENT = "kevinclaw26@gmail.com"
EMAIL_TIME = "08:00"
```

---

## Files

**Core Modules:**
- `advisor.py` - Main orchestrator
- `portfolio_analyzer.py` - Robinhood connection
- `sentiment_engine.py` - News sentiment analysis
- `quant_engine.py` - Technical indicators
- `recommendation_engine.py` - Signal combination
- `config.py` - All settings

**Data Storage:**
- `data/portfolio.json` - Current positions
- `data/analysis_YYYYMMDD.json` - Daily analysis results
- `data/daily_report_YYYYMMDD.txt` - Email reports
- `data/trade_history.json` - Track recommendations

**GUI (Coming Soon):**
- `dashboard.py` - Flask web interface
- `templates/dashboard.html` - Portfolio view

---

## Usage

### Daily Workflow

**8:00 AM** - Receive email with recommendations

**8:05 AM** - Review recommendations (5 minutes)
- Check if signals make sense
- Verify stocks on Robinhood app
- Review news headlines yourself

**8:10 AM** - Place limit orders (3 minutes)
- Open Robinhood
- Enter the exact limit prices from email
- Set orders as "Good for Day"

**Rest of Day** - Let orders execute
- Limit orders will fill if price reaches your level
- If not filled by market close, orders expire
- Check end of day to see what executed

**Next Morning** - Repeat

### Weekly Review

Every Sunday:
```bash
python analyzer.py --weekly-review
```

Shows:
- Which recommendations executed
- Which stocks gained/lost
- Overall strategy performance
- Recommendations to adjust

---

## Safety Features

✅ **Swing Trading Focus** - No day trading triggers
✅ **Position Limits** - Max 8% in any single stock
✅ **Daily Trade Limit** - Max 3 recommendations per day
✅ **Signal Threshold** - Only strong signals (≥65%)
✅ **Limit Orders** - Never market orders (wait for good prices)
✅ **Stop Losses** - Built into signal logic
✅ **Cash Reserve** - Always keep 5% cash

---

## Incremental Build Plan

**Phase 1: Core (DONE)**
- ✅ Portfolio analyzer
- ✅ Sentiment engine
- ✅ Quant engine
- ✅ Recommendation engine
- ✅ Text email reports

**Phase 2: Automation (Next)**
- [ ] Integrate with nanoclaw scheduler
- [ ] Automated 8 AM email delivery
- [ ] Historical performance tracking

**Phase 3: GUI (Later)**
- [ ] Flask web dashboard
- [ ] Visual portfolio view
- [ ] Interactive recommendation review
- [ ] Performance charts

**Phase 4: Enhancements (Future)**
- [ ] Live Twitter sentiment
- [ ] More advanced technical indicators
- [ ] Machine learning signal optimization
- [ ] Options analysis

---

## Testing

### Test Individual Components

```bash
# Test portfolio connection
python portfolio_analyzer.py

# Test sentiment analysis
python sentiment_engine.py

# Test technical analysis
python quant_engine.py

# Test recommendations
python recommendation_engine.py

# Test full system
python advisor.py
```

### Test with Mock Data

The system works with or without Robinhood login:
- **With login:** Analyzes your actual 20 stocks
- **Without login:** Uses mock portfolio for testing

This lets you test everything before connecting real account.

---

## Robinhood API Notes

**Important:** Robinhood doesn't have an official API.

We use `robin-stocks` (unofficial Python library):
- ✅ Can fetch portfolio data
- ✅ Can get positions and prices
- ✅ Can place orders programmatically
- ⚠️ May break if Robinhood changes their system
- ⚠️ Use at your own risk

**Recommendation:** Start by just using this for analysis. Place orders manually in the Robinhood app. Once you trust the recommendations, you can enable automatic order placement.

---

## Performance Tracking

The system tracks:
- Which recommendations you followed
- Which orders executed
- Which positions gained/lost
- Overall strategy performance vs. S&P 500

View anytime:
```bash
python analyzer.py --performance
```

---

## Troubleshooting

**"Module not found" error:**
```bash
pip install -r requirements.txt
```

**Robinhood login fails:**
- Check username/password in .env
- If using 2FA, set ROBINHOOD_MFA_CODE
- Try logging in via Robinhood app first

**No recommendations generated:**
- Normal! System is conservative
- Will only recommend when signals are strong
- Try lowering MIN_SIGNAL_STRENGTH in config.py

**Email not sending:**
- Check EMAIL_ENABLED in config.py
- Reports are saved to data/ folder either way

---

## Next Steps

1. **Test the system** with mock data
2. **Connect your Robinhood** account
3. **Run one manual analysis** in the morning
4. **Review the recommendations** - do they make sense?
5. **Place 1-2 limit orders** manually to test
6. **Track results** for a week
7. **Automate** once you trust the system

---

## Disclaimer

This tool provides automated analysis and recommendations based on technical and sentiment data. It is NOT financial advice. Always do your own research before making investment decisions. Past performance does not guarantee future results.

- Start small
- Verify recommendations
- Use limit orders
- Track your results
- Adjust as needed

---

**Built specifically for Kevin's $4,500 portfolio - 20 stocks, swing trading, daily email workflow**

Ready to use! 🎯
