# Using CSV Portfolio (No Robinhood Login!)

**This is the secure, easy way to use the advisor without exposing your Robinhood credentials.**

---

## Step 1: Export Your Robinhood Portfolio

### Option A: Manual Entry (Simplest)

Just look at your Robinhood app and type the data into `data/portfolio.csv`:

```csv
symbol,shares,avg_cost
AAPL,10,150.00
NVDA,5,120.00
TSLA,8,200.00
```

### Option B: Robinhood CSV Export (If Available)

1. Open Robinhood app/website
2. Look for "Export" or "Download" option (usually in account settings)
3. Download as CSV
4. Save to `data/portfolio.csv`

### Option C: From Screenshot

1. Take screenshot of your Robinhood portfolio
2. Manually transcribe to CSV format
3. Save as `data/portfolio.csv`

---

## Step 2: Format Your CSV

The CSV needs exactly 3 columns:

```csv
symbol,shares,avg_cost
AAPL,10.5,175.25
NVDA,5,145.00
TSLA,12,250.75
MSFT,8,380.50
GOOGL,15,135.20
```

**Column descriptions:**
- `symbol`: Stock ticker (e.g., AAPL, NVDA)
- `shares`: Number of shares you own (can have decimals like 10.5)
- `avg_cost`: Your average cost per share in dollars

**Example from your portfolio:**
If you bought 10 shares of AAPL at different prices:
- 5 shares @ $150
- 5 shares @ $200
- Average cost = (5×150 + 5×200) / 10 = $175

---

## Step 3: Run the Advisor

```bash
python advisor.py
```

That's it! It will:
1. Read your CSV
2. Fetch current prices from yfinance (free, no login)
3. Calculate your returns
4. Generate recommendations

---

## What You Get

### Portfolio Summary
```
Portfolio Value: $8,450.00
Total Return: +$1,200.00 (+16.5%)
Positions: 20
```

### Today's Recommendations
```
🟢 BUY: AMD
   Current: $145.20
   → Limit BUY: $144.50 (3 shares)
   Signal: 78% (Sentiment: BULLISH, Technical: BUY)

🔴 SELL: TSLA
   Current: $238.00
   Your cost: $250.75 (-$12.75/share, -5.1%)
   → Limit SELL: $238.50 (6 shares of 12)
   Signal: 28% (Cut losses, bearish trend)
```

---

## Updating Your Portfolio

### Weekly Updates (Recommended)

Every Sunday, update your CSV with any trades you made:

```csv
symbol,shares,avg_cost
AAPL,12,160.00    # Bought 2 more shares
NVDA,5,145.00     # No change
TSLA,6,250.75     # Sold 6 shares (per advisor recommendation)
```

### After Each Trade

If you want real-time accuracy, update the CSV whenever you make a trade.

### Automatic Tracking

You can use a spreadsheet to track trades and calculate average cost automatically:

**Google Sheets formula:**
```
=AVERAGE_COST(purchases_range)
```

---

## Advantages of CSV Method

✅ **No login required** - Keep your Robinhood credentials secure
✅ **Works with any broker** - Not limited to Robinhood
✅ **Full control** - You decide what data to share
✅ **Manual verification** - You always know what the advisor sees
✅ **Backup** - CSV is a backup of your portfolio

---

## Disadvantages

❌ **Manual updates** - You need to update CSV when you trade
❌ **Not real-time** - Position values updated when you update CSV
❌ **No automatic sync** - Won't catch intraday trades automatically

**Solution:** Just update the CSV weekly or after trades. The analysis is still valuable!

---

## CSV Template

Copy this to `data/portfolio.csv`:

```csv
symbol,shares,avg_cost
AAPL,0,0.00
NVDA,0,0.00
TSLA,0,0.00
MSFT,0,0.00
GOOGL,0,0.00
AMD,0,0.00
AMZN,0,0.00
META,0,0.00
NFLX,0,0.00
DIS,0,0.00
V,0,0.00
MA,0,0.00
JPM,0,0.00
BAC,0,0.00
WMT,0,0.00
COST,0,0.00
HD,0,0.00
LOW,0,0.00
PG,0,0.00
KO,0,0.00
```

Replace `0,0.00` with your actual shares and average cost.

---

## Pro Tips

1. **Use a spreadsheet** (Google Sheets, Excel) to maintain your portfolio, then export as CSV
2. **Version control** - Keep dated backups like `portfolio_2026-02-27.csv`
3. **Add comments** - You can add a `notes` column for your reference
4. **Automate updates** - Set a reminder to update weekly

---

## Example Workflow

**Sunday Evening:**
1. Open your portfolio CSV
2. Review last week's trades
3. Update shares/avg_cost for any changes
4. Save CSV
5. Run `python advisor.py`
6. Review recommendations for the week
7. Place limit orders Monday morning

**Daily (Optional):**
- Run advisor to see if recommendations changed
- Adjust limit orders if needed

---

**Ready to use! Edit `data/portfolio.csv` with your stocks and run `python advisor.py`** 🚀
