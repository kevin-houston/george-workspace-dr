# Autoresearch Insights — Round 1
Generated: 2026-03-27 22:39
Tickers: 88  |  Strategies: 19  |  Metric: raw return

## Top 20 Combinations by Raw Return

Rank  Ticker  Strategy     Type           Return%   CAGR%  Sharpe    vs B&H
----------------------------------------------------------------------
1     TSLA    PM_1_0       long          18268.4%   41.4%    1.06  -4946.8%
2     TSLA    LV_60        short         12235.8%   37.7%    0.95 -10979.4%
3     TSLA    MA_10_30     long          11595.8%   37.2%    0.98 -11619.4%
4     TSLA    EMA_12_26    long           6214.6%   31.7%    0.88 -17000.5%
5     NFLX    MA_50_200    long           4273.8%   28.6%    0.87  +1181.5%
6     NFLX    LV_60        long           3682.6%   27.3%    0.88   +590.3%
7     NFLX    PM_3_0       long           3049.1%   25.8%    0.82    -43.2%
8     TSLA    MA_50_200    long           2869.6%   25.3%    0.71 -20345.5%
9     TSLA    MA_20_50     long           2581.2%   24.4%    0.73 -20634.0%
10    TSLA    PM_6_1       long           2498.7%   24.2%    0.69 -20716.4%
11    NFLX    PM_6_1       long           2313.0%   23.6%    0.77   -779.3%
12    NFLX    PM_12_1      long           2212.7%   23.2%    0.75   -879.6%
13    NFLX    PM_1_0       long           2190.1%   23.1%    0.78   -902.2%
14    TSLA    PM_3_0       long           2088.8%   22.8%    0.69 -21126.3%
15    AAPL    PM_1_0       long           1885.0%   22.0%    1.19   -431.2%
16    META    MA_20_50     long           1883.9%   24.1%    0.90   +540.5%
17    TSLA    MR_20_15     short          1826.3%   21.7%    0.93 -21388.9%
18    NFLX    EMA_12_26    long           1735.3%   21.3%    0.73  -1357.0%
19    META    PM_3_0       long           1706.8%   23.3%    0.89   +363.3%
20    TSLA    PM_12_1      long           1637.3%   20.9%    0.64 -21577.9%

## Bottom 10 Combinations by Raw Return

Rank  Ticker  Strategy     Type           Return%
--------------------------------------------------
1     HUM     PM_1_0       long_short      -95.3%
2     TSLA    RSI_14       long_short      -96.4%
3     TSLA    MR_20_15     long_short      -96.7%
4     F       PM_12_1      long_short      -96.8%
5     DG      LV_60        long_short      -96.9%
6     PRU     PM_12_1      long_short      -97.0%
7     HUM     EMA_12_26    long_short      -97.0%
8     INTC    MA_10_30     long_short      -97.7%
9     HUM     MA_20_50     long_short      -98.4%
10    TSLA    LV_60        long_short      -99.9%

## Strategy Family Ranking (avg raw return across all tickers)

Family                   Avg%     Max%     Min%
------------------------------------------------
volatility             168.4% 12235.8%   -99.9%
momentum               162.9% 18268.4%   -97.0%
trend                  147.5% 11595.8%   -98.4%
ml                      40.1%   628.9%   -94.8%
mean_reversion          28.0%  1826.3%   -96.7%
breakout                21.9%   798.8%   -86.9%

## Strategy Ranking (best position type, avg across tickers)

Strategy     Type         Family             Avg%     Max%
----------------------------------------------------------
PM_1_0       long         momentum         443.7% 18268.4%
MA_10_30     long         trend            341.3% 11595.8%
MA_50_200    long         trend            316.1%  4273.8%
LV_60        short        volatility       306.6% 12235.8%
PM_12_1      long         momentum         295.5%  2212.7%
PM_6_1       long         momentum         272.7%  2498.7%
EMA_12_26    long         trend            265.8%  6214.6%
PM_3_0       long         momentum         227.2%  3049.1%
LV_60        long         volatility       219.8%  3682.6%
MA_20_50     long         trend            210.1%  2581.2%
MA_20_50     short        trend            192.3%   703.1%
PM_3_0       short        momentum         189.4%   840.8%
EMA_12_26    short        trend            180.6%   657.8%
PM_6_1       short        momentum         179.4%  1079.8%
MA_10_30     short        trend            174.8%   607.6%
PM_1_0       short        momentum         167.0%   591.5%
MA_50_200    short        trend            139.6%   610.6%
PM_12_1      short        momentum         124.7%   760.7%
KNN_5        long         ml                70.6%   405.6%
PM_12_1      long_short   momentum          68.4%  1212.5%

## Beat Buy-and-Hold Analysis
Combinations that beat B&H: 150 / 4959 (3.0%)

Strategy       Beat%  Count
----------------------------
PM_3_0            6%   16/261
LV_60             6%   15/261
MA_10_30          6%   15/261
PM_12_1           6%   15/261
PM_1_0            5%   14/261
MA_50_200         5%   14/261
MA_20_50          5%   14/261
EMA_12_26         5%   13/261
PM_6_1            5%   13/261
DC_55             2%    4/261
KNN_5             2%    4/261
MR_20_15          1%    3/261
DC_20             1%    2/261
RSI_21            1%    2/261
KNN_10            1%    2/261
RSI_14            0%    1/261
MR_60_2           0%    1/261
MR_20_2           0%    1/261
BB_20             0%    1/261

## Next Round Recommendations

- Best performing family: *volatility*
- Top strategies to refine: PM_1_0, MA_10_30, MA_50_200
- Overall B&H beat rate: 3.0%
- Suggested focus: parameter sweep on volatility family window lengths
- Consider: adding MACD histogram, volume-weighted signals, sector rotation

---
*Generated by autoresearch harness round 1*