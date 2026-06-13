# H289: News Entropy Regime Signal (arXiv:2309.05560 'New News is Bad News')
# Proxy: month-over-month KL divergence of NewsAPI topic distributions
# High KL divergence = novel/unusual news = defensive posture (BIL)
# Layer onto H249 4-state regime framework as 3rd signal
# IS: 2015-2019, OOS: 2020-2025
# Gate: OOS Sharpe improvement > 0.05 vs H249 baseline (1.031)
#
# KL divergence proxy:
# 1. Fetch 30d and prior-30d news for S&P 500 query via NewsAPI
# 2. Build word frequency vectors (top 200 words, no stopwords)
# 3. Compute KL(current_30d || prior_30d)
# 4. If KL > threshold: high entropy (unusual news) → defensive
#
# Monthly rebalance signal:
# existing H249: SPY 200MA x VIX 4-state
# + H289 layer: if entropy_kl > 0.30 → override to BIL regardless of H249 state
#
# Limitation: NewsAPI free tier has limited history (1 year)
# For historical test, need to substitute with GDELT or Common Crawl news
# Alternative proxy: VIX term structure slope (cheaper, already have data)
print('H289 scaffold - to be implemented')
