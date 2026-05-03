#!/usr/bin/env python3
"""
Robinhood Portfolio Advisor - Configuration
Customized for 20 stocks, $4500 portfolio, no day trading
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the advisor directory
load_dotenv(Path(__file__).parent / ".env")

# Portfolio Settings
PORTFOLIO_SIZE = 4500
NUM_HOLDINGS = 20
AVG_POSITION_SIZE = PORTFOLIO_SIZE / NUM_HOLDINGS  # ~$225 per stock

# Trading Strategy (Swing Trading - Days to Weeks)
STRATEGY_TYPE = "swing"  # Not day trading
MIN_HOLD_DAYS = 2  # Don't flip positions daily
TARGET_RETURN_PER_TRADE = 0.05  # 5% target per trade
MAX_LOSS_PER_TRADE = 0.03  # 3% stop loss

# Daily Recommendations
MAX_DAILY_TRADES = 3  # Don't overwhelm with too many orders
MIN_SIGNAL_STRENGTH = 0.65  # Only strong signals (0-1 scale)
LIMIT_ORDER_BUFFER = 0.005  # 0.5% below current for buys, above for sells

# Risk Management
MAX_POSITION_SIZE = 0.08  # 8% max in any single stock
MIN_POSITION_SIZE = 0.03  # 3% minimum position
REBALANCE_THRESHOLD = 0.10  # Rebalance if position drifts >10%
CASH_RESERVE = 0.05  # Keep 5% in cash

# Sentiment Analysis Settings
SENTIMENT_WEIGHT = 0.4  # 40% weight on sentiment
TECHNICAL_WEIGHT = 0.6  # 60% weight on technicals

NEWS_LOOKBACK_DAYS = 3  # Analyze news from last 3 days
MIN_NEWS_ARTICLES = 2  # Need at least 2 articles for sentiment
SOCIAL_SENTIMENT_ENABLED = True  # Use Twitter/Reddit sentiment

# Technical Analysis Settings
USE_INDICATORS = [
    'rsi',           # Relative Strength Index
    'macd',          # Moving Average Convergence Divergence
    'sma_50',        # 50-day Simple Moving Average
    'sma_200',       # 200-day Simple Moving Average
    'volume',        # Volume trends
    'support_resistance',  # Key price levels
]

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_WINDOW = 14

# Email Settings
EMAIL_RECIPIENT = "kevinclaw26@gmail.com"
EMAIL_TIME = "08:00"  # 8 AM daily report
EMAIL_SUBJECT_PREFIX = "📊 Portfolio Morning Brief"

# Enable email sending (set False for testing)
EMAIL_ENABLED = True

# Robinhood API Settings
ROBINHOOD_USERNAME = os.getenv("ROBINHOOD_USERNAME", "")
ROBINHOOD_PASSWORD = os.getenv("ROBINHOOD_PASSWORD", "")
ROBINHOOD_MFA_CODE = os.getenv("ROBINHOOD_MFA_CODE", "")  # If using 2FA

# Data Storage
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"
LOGS_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
HISTORY_FILE = DATA_DIR / "trade_history.json"
PERFORMANCE_FILE = DATA_DIR / "performance.json"

# API Keys (from environment)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")  # newsapi.org
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")  # alphavantage.co

# GUI Settings
GUI_PORT = 8080
GUI_HOST = "127.0.0.1"  # Local only
GUI_AUTO_REFRESH = 300  # Refresh every 5 minutes

# Scheduler Settings
ANALYSIS_SCHEDULE = "0 8 * * *"  # Daily at 8 AM (cron format)
PORTFOLIO_SYNC_SCHEDULE = "0 */4 * * *"  # Every 4 hours

# Logging
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Testing Mode
PAPER_TRADING = False  # Set True to test without real orders
DRY_RUN = False  # Set True to analyze without sending emails

# Market Hours (ET)
MARKET_OPEN_HOUR = 9  # 9:30 AM ET (we'll check at 9 AM)
MARKET_CLOSE_HOUR = 16  # 4:00 PM ET

# Watchlist (stocks to monitor but not necessarily hold)
WATCHLIST = [
    # Add tickers you want to monitor for entry points
    # Examples: 'AAPL', 'NVDA', 'AMD', 'COIN'
]

# Blacklist (stocks to never recommend)
BLACKLIST = [
    # Add tickers to avoid
    # Examples: 'GME', 'AMC' (if you want to avoid meme stocks)
]

# Performance Tracking
BENCHMARK_TICKER = "SPY"  # Compare performance to S&P 500
TRACK_DAILY = True
TRACK_WEEKLY = True
TRACK_MONTHLY = True

# Recommendation Thresholds
STRONG_BUY_THRESHOLD = 0.80  # Signal strength for strong buy
BUY_THRESHOLD = 0.65  # Signal strength for buy
HOLD_THRESHOLD = 0.45  # Between 0.45-0.65 = hold
SELL_THRESHOLD = 0.35  # Below 0.35 = sell
STRONG_SELL_THRESHOLD = 0.20  # Below 0.20 = strong sell

print(f"Configuration loaded for {NUM_HOLDINGS} stock portfolio (${PORTFOLIO_SIZE:,.0f})")
