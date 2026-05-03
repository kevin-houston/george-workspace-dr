# Candlestick Pattern Autoresearch — Results
Date: 2026-03-29
Scope: 25 patterns × 39 Fortune 100 tickers × 4 hold periods × 2 directions = 7,800 backtests
Universe: Fortune 100 (AAPL, MSFT, NVDA, JPM, etc.) — 2019-01-01 to 2026-03-28

## TL;DR
Candlestick patterns have *marginal edge at best*. Bullish patterns in a secular bull market show
positive returns — but only because of market drift, not pattern predictability. Shorting bearish
patterns is a money loser. The patterns with the best Sharpe (~0.4) are catching momentum, not reversal.

## Top 5 Patterns (by Sharpe)
1. SpinningTop — bullish, 10d — AvgRet 219.7%, Sharpe 0.419, WinRate 94.9%
2. BullishHarami — bullish, 10d — AvgRet 145.8%, Sharpe 0.403, WinRate 89.7%
3. SpinningTop — bullish, 5d — AvgRet 106.9%, Sharpe 0.375, WinRate 94.9%
4. BullishHarami — bullish, 5d — AvgRet 67.8%, Sharpe 0.348, WinRate 89.7%
5. SpinningTop — bullish, 3d — AvgRet 61.6%, Sharpe 0.307, WinRate 89.7%

## Bottom 5 (worst — avoid as trading signals)
1. BearishHarami — bearish, 10d — AvgRet -58.7%, Sharpe -0.395
2. SpinningTop — bearish, 10d — AvgRet -62.7%, Sharpe -0.366
3. TweezerTop — bearish, 10d — AvgRet -45.0%, Sharpe -0.354
4. DarkCloudCover — bearish, 10d — AvgRet -45.9%, Sharpe -0.336
5. DarkCloudCover — bearish, 5d — AvgRet -36.3%, Sharpe -0.333

## Category Ranking
- Single-candle: avg 6.4%, Sharpe -0.004 (best category)
- Three-candle: avg -0.4%, Sharpe -0.013
- Two-candle: avg 2.1%, Sharpe -0.030

## Optimal Hold Period
- 3-day hold: Sharpe -0.002 (best)
- 10-day hold: Sharpe -0.014
- 5-day hold: Sharpe -0.018
- 1-day hold: Sharpe -0.021

## Key Insights

### 1. Patterns don't beat buy-and-hold
B&H avg benchmark: 2,175.6% cumulative over backtest period.
Only SpinningTop/10d came close (2.6% of stocks beat B&H). The rest: 0%.

### 2. Bullish bias dominates
The patterns with positive Sharpe ratios are all bullish signals in a secular bull market.
They're not predicting reversals — they're capturing market drift.

### 3. Reversal patterns fail
"Bearish reversal" patterns (Dark Cloud Cover, Evening Star, TweezerTop, BearishHarami)
are systematically wrong in a bull market. Worst performers by wide margin.

### 4. Simpler > complex
Single-candle patterns slightly edge out 2-candle and 3-candle patterns.
MorningStar (3-candle, the "gold standard" reversal signal) ranks only #8 by Sharpe (0.270).

### 5. SpinningTop paradox
SpinningTop is an "indecision" candle — small body, equal shadows. It ranks #1.
This suggests it works as a continuation pattern during quiet days in an uptrend,
not because it predicts direction, but because it appears during low-volatility consolidation
before the trend resumes.

## Trading Implication
If you're going to use candlestick patterns:
- USE: SpinningTop, BullishHarami as *confirmation* of existing uptrend (not standalone signal)
- IGNORE: All bearish reversal patterns in equity long-only context
- HOLD: 3-10 days is optimal — 1-day is noise, beyond 10 days signal decays
- COMBINE: Pattern + macro regime (our classifier) would likely improve Sharpe materially

## Next Experiment Idea
Layer macro regime on candle signals:
- Only take bullish candle signals when macro regime = calm/easing/low_stress
- Skip bullish candle signals when macro regime = oil_shock/stress
- This is how professional technicians actually use these patterns

