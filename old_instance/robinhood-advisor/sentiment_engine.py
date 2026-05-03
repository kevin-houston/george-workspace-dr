#!/usr/bin/env python3
"""
Sentiment Analysis Engine - Simplified Version
Analyzes news headlines for stock sentiment (no social media for MVP)
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List
import config

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class SentimentEngine:
    """Analyzes market sentiment from news headlines"""

    def __init__(self):
        self.news_api_key = config.NEWS_API_KEY

        # Simplified sentiment word lists
        self.positive_words = [
            'surge', 'soar', 'rally', 'jump', 'gain', 'rise', 'up', 'bull', 'bullish',
            'beat', 'exceed', 'strong', 'growth', 'profit', 'revenue', 'upgrade',
            'buy', 'outperform', 'positive', 'optimistic', 'opportunity', 'breakthrough',
            'innovation', 'success', 'milestone', 'record', 'high', 'peak'
        ]

        self.negative_words = [
            'plunge', 'crash', 'fall', 'drop', 'decline', 'down', 'bear', 'bearish',
            'miss', 'disappoint', 'weak', 'loss', 'deficit', 'downgrade', 'sell',
            'underperform', 'negative', 'pessimistic', 'risk', 'concern', 'worry',
            'fail', 'layoff', 'cut', 'reduce', 'low', 'bottom'
        ]

    def get_news(self, symbol: str, days: int = 3) -> List[Dict]:
        """
        Fetch news articles for a stock symbol
        Using simplified approach - just headlines
        """
        # For MVP, use free news sources or mock data
        # In production, you'd use NewsAPI, Alpha Vantage, or similar

        # Mock implementation for testing
        mock_news = [
            {
                'title': f'{symbol} beats earnings expectations',
                'published': datetime.now().isoformat(),
                'source': 'Mock News'
            },
            {
                'title': f'Analysts upgrade {symbol} to buy',
                'published': (datetime.now() - timedelta(days=1)).isoformat(),
                'source': 'Mock News'
            }
        ]

        logger.info(f"Fetched {len(mock_news)} news articles for {symbol}")
        return mock_news

        # Real implementation (uncomment when you have API key):
        # if not self.news_api_key:
        #     logger.warning("No News API key configured")
        #     return mock_news
        #
        # from_date = (datetime.now() - timedelta(days=days)).isoformat()
        # url = f"https://newsapi.org/v2/everything?q={symbol}&from={from_date}&sortBy=publishedAt&apiKey={self.news_api_key}"
        #
        # try:
        #     response = requests.get(url, timeout=10)
        #     data = response.json()
        #     articles = data.get('articles', [])
        #     return articles[:20]  # Top 20 articles
        # except Exception as e:
        #     logger.error(f"Error fetching news: {e}")
        #     return []

    def analyze_headline(self, headline: str) -> float:
        """
        Analyze sentiment of a single headline
        Returns: -1.0 (very bearish) to +1.0 (very bullish)
        """
        headline_lower = headline.lower()

        positive_count = sum(1 for word in self.positive_words if word in headline_lower)
        negative_count = sum(1 for word in self.negative_words if word in headline_lower)

        total = positive_count + negative_count

        if total == 0:
            return 0.0  # Neutral

        sentiment = (positive_count - negative_count) / total
        return sentiment

    def analyze_stock_sentiment(self, symbol: str) -> Dict:
        """
        Analyze overall sentiment for a stock
        Returns sentiment score and metadata
        """
        news = self.get_news(symbol, days=config.NEWS_LOOKBACK_DAYS)

        if len(news) < config.MIN_NEWS_ARTICLES:
            logger.warning(f"Insufficient news for {symbol} ({len(news)} articles)")
            return {
                'symbol': symbol,
                'sentiment_score': 0.0,
                'confidence': 0.0,
                'article_count': len(news),
                'rating': 'NEUTRAL',
                'reason': 'Insufficient news data'
            }

        # Analyze each headline
        sentiments = []
        for article in news:
            headline = article.get('title', '')
            if headline:
                sentiment = self.analyze_headline(headline)
                sentiments.append(sentiment)

        # Calculate aggregate sentiment
        if not sentiments:
            avg_sentiment = 0.0
        else:
            avg_sentiment = sum(sentiments) / len(sentiments)

        # Confidence based on number of articles and consistency
        confidence = min(len(news) / 10, 1.0)  # Max confidence at 10+ articles

        # Convert to rating
        if avg_sentiment > 0.3:
            rating = 'BULLISH'
        elif avg_sentiment > 0.1:
            rating = 'SLIGHTLY_BULLISH'
        elif avg_sentiment < -0.3:
            rating = 'BEARISH'
        elif avg_sentiment < -0.1:
            rating = 'SLIGHTLY_BEARISH'
        else:
            rating = 'NEUTRAL'

        return {
            'symbol': symbol,
            'sentiment_score': avg_sentiment,
            'confidence': confidence,
            'article_count': len(news),
            'rating': rating,
            'reason': f'Based on {len(news)} recent articles'
        }

    def analyze_multiple_stocks(self, symbols: List[str]) -> Dict[str, Dict]:
        """Analyze sentiment for multiple stocks"""
        results = {}

        for symbol in symbols:
            try:
                sentiment = self.analyze_stock_sentiment(symbol)
                results[symbol] = sentiment
                logger.info(f"{symbol}: {sentiment['rating']} ({sentiment['sentiment_score']:+.2f})")
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                results[symbol] = {
                    'symbol': symbol,
                    'sentiment_score': 0.0,
                    'confidence': 0.0,
                    'article_count': 0,
                    'rating': 'ERROR',
                    'reason': str(e)
                }

        return results


def test_sentiment_engine():
    """Test the sentiment engine"""
    print("\n" + "="*60)
    print("  SENTIMENT ENGINE TEST")
    print("="*60 + "\n")

    engine = SentimentEngine()

    # Test headline analysis
    test_headlines = [
        "Apple stock surges on strong earnings beat",
        "Tesla shares plunge on disappointing delivery numbers",
        "Microsoft announces new product line",
        "AMD stock falls after analyst downgrade"
    ]

    print("Testing headline sentiment analysis:\n")
    for headline in test_headlines:
        sentiment = engine.analyze_headline(headline)
        print(f"Headline: {headline}")
        print(f"Sentiment: {sentiment:+.2f}\n")

    # Test stock analysis
    print("\n" + "-"*60)
    print("Testing stock sentiment analysis:\n")

    test_symbols = ['AAPL', 'NVDA', 'TSLA']
    results = engine.analyze_multiple_stocks(test_symbols)

    for symbol, data in results.items():
        print(f"{symbol}: {data['rating']} ({data['sentiment_score']:+.2f})")
        print(f"  Confidence: {data['confidence']:.0%}")
        print(f"  Articles: {data['article_count']}")
        print(f"  {data['reason']}\n")

    print("="*60 + "\n")


if __name__ == "__main__":
    test_sentiment_engine()
