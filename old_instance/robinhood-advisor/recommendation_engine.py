#!/usr/bin/env python3
"""
Recommendation Engine - Combines sentiment + quant analysis
Generates specific limit order recommendations
"""

import logging
from typing import Dict, List
from datetime import datetime
import config

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Generates trading recommendations from combined analysis"""

    def __init__(self):
        pass

    def combine_signals(self, sentiment_data: Dict, quant_data: Dict) -> float:
        """
        Combine sentiment and quantitative signals
        Returns: 0.0 (strong sell) to 1.0 (strong buy)
        """
        # Convert sentiment score (-1 to +1) to 0-1 scale
        sentiment_score = (sentiment_data.get('sentiment_score', 0) + 1) / 2

        # Weight sentiment confidence
        sentiment_confidence = sentiment_data.get('confidence', 0.5)
        weighted_sentiment = sentiment_score * sentiment_confidence

        # Get quant signal (already 0-1)
        quant_signal = quant_data.get('signal_strength', 0.5)

        # Combine with configured weights
        combined = (
            weighted_sentiment * config.SENTIMENT_WEIGHT +
            quant_signal * config.TECHNICAL_WEIGHT
        )

        return combined

    def generate_limit_price(self, current_price: float, action: str) -> float:
        """
        Generate limit order price
        BUY: Slightly below current (wait for dip)
        SELL: Slightly above current (wait for bounce)
        """
        if action == 'BUY':
            # Buy at X% below current
            limit_price = current_price * (1 - config.LIMIT_ORDER_BUFFER)
        elif action == 'SELL':
            # Sell at X% above current
            limit_price = current_price * (1 + config.LIMIT_ORDER_BUFFER)
        else:
            limit_price = current_price

        return round(limit_price, 2)

    def calculate_position_size(self,
                                portfolio_value: float,
                                current_price: float,
                                action: str,
                                current_shares: float = 0) -> float:
        """
        Calculate recommended position size in shares (supports fractional shares)
        """
        if action == 'BUY':
            # Target position size based on portfolio
            target_value = portfolio_value * config.MAX_POSITION_SIZE
            shares = target_value / current_price
            # Round to 2 decimal places for fractional shares
            shares = round(shares, 2)
            # For very small positions, ensure at least 0.01 share
            return max(0.01, shares)

        elif action == 'SELL':
            # Sell portion or all
            if current_shares > 0:
                # Sell 50% on SELL, 100% on STRONG_SELL
                # Round to 2 decimal places to match typical fractional share precision
                sell_shares = round(current_shares / 2, 2)
                # If the result would be less than 0.01 shares, sell all
                if sell_shares < 0.01:
                    return round(current_shares, 2)
                return sell_shares
            return 0

        return 0

    def generate_recommendation(self,
                                 symbol: str,
                                 current_price: float,
                                 sentiment_data: Dict,
                                 quant_data: Dict,
                                 portfolio_value: float,
                                 current_position: Dict = None) -> Dict:
        """
        Generate complete recommendation for a stock
        """
        # Combine signals
        combined_signal = self.combine_signals(sentiment_data, quant_data)

        # Determine action
        if combined_signal >= config.STRONG_BUY_THRESHOLD:
            action = 'STRONG_BUY'
            order_type = 'BUY'
        elif combined_signal >= config.BUY_THRESHOLD:
            action = 'BUY'
            order_type = 'BUY'
        elif combined_signal <= config.STRONG_SELL_THRESHOLD:
            action = 'STRONG_SELL'
            order_type = 'SELL'
        elif combined_signal <= config.SELL_THRESHOLD:
            action = 'SELL'
            order_type = 'SELL'
        else:
            action = 'HOLD'
            order_type = 'HOLD'

        # Current position info
        current_shares = current_position['quantity'] if current_position else 0
        avg_cost = current_position['avg_buy_price'] if current_position else 0
        current_return = 0
        if current_position:
            current_return = ((current_price / avg_cost) - 1) * 100 if avg_cost > 0 else 0

        # Generate limit price and size
        limit_price = self.generate_limit_price(current_price, order_type)
        shares = self.calculate_position_size(
            portfolio_value, current_price, order_type, current_shares
        )

        # Robinhood limitation: Cannot place limit orders on fractional shares
        # For SELL orders with fractional shares, recommend market order instead
        is_fractional = shares < 1 or (shares % 1 != 0)

        if order_type == 'SELL' and is_fractional:
            # Change to market order for fractional sells
            order_type = 'MARKET_SELL'
            limit_price = current_price  # Use current price for market orders

        # Build rationale
        rationale_parts = []

        # Sentiment rationale
        sent_rating = sentiment_data.get('rating', 'NEUTRAL')
        rationale_parts.append(f"Sentiment: {sent_rating}")

        # Technical rationale
        quant_rec = quant_data.get('recommendation', 'HOLD')
        rationale_parts.append(f"Technical: {quant_rec}")

        # RSI
        if 'indicators' in quant_data:
            rsi = quant_data['indicators'].get('rsi', 50)
            if rsi < config.RSI_OVERSOLD:
                rationale_parts.append(f"RSI oversold ({rsi:.0f})")
            elif rsi > config.RSI_OVERBOUGHT:
                rationale_parts.append(f"RSI overbought ({rsi:.0f})")

        # Add note about fractional shares
        if order_type == 'MARKET_SELL':
            rationale_parts.append("Market order (fractional shares)")

        rationale = ", ".join(rationale_parts)

        recommendation = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'order_type': order_type,
            'signal_strength': combined_signal,
            'current_price': current_price,
            'limit_price': limit_price,
            'shares': shares,
            'order_value': limit_price * shares if shares > 0 else 0,
            'current_position': {
                'shares': current_shares,
                'avg_cost': avg_cost,
                'current_return_pct': current_return
            },
            'rationale': rationale,
            'sentiment': sentiment_data,
            'technical': quant_data
        }

        return recommendation

    def filter_actionable_recommendations(self,
                                         recommendations: List[Dict],
                                         max_trades: int = None) -> List[Dict]:
        """
        Filter recommendations to only actionable items
        Returns top N by signal strength
        """
        max_trades = max_trades or config.MAX_DAILY_TRADES

        # Filter out HOLD
        actionable = [r for r in recommendations if r['order_type'] != 'HOLD']

        # Filter by minimum signal strength
        actionable = [r for r in actionable
                     if (r['signal_strength'] >= config.MIN_SIGNAL_STRENGTH
                         if r['order_type'] == 'BUY'
                         else r['signal_strength'] <= (1 - config.MIN_SIGNAL_STRENGTH))]

        # Sort by signal strength (distance from 0.5)
        actionable.sort(key=lambda x: abs(x['signal_strength'] - 0.5), reverse=True)

        # Return top N
        return actionable[:max_trades]

    def categorize_recommendations(self, recommendations: List[Dict]) -> Dict:
        """Categorize recommendations into buy/sell/hold buckets"""
        categorized = {
            'strong_buy': [],
            'buy': [],
            'hold': [],
            'sell': [],
            'strong_sell': []
        }

        for rec in recommendations:
            action = rec['action'].lower()
            if action in categorized:
                categorized[action].append(rec)

        return categorized


def test_recommendation_engine():
    """Test the recommendation engine"""
    print("\n" + "="*60)
    print("  RECOMMENDATION ENGINE TEST")
    print("="*60 + "\n")

    engine = RecommendationEngine()

    # Mock data
    sentiment_data = {
        'sentiment_score': 0.6,
        'confidence': 0.8,
        'rating': 'BULLISH'
    }

    quant_data = {
        'signal_strength': 0.75,
        'recommendation': 'BUY',
        'indicators': {
            'rsi': 35
        }
    }

    # Generate recommendation
    rec = engine.generate_recommendation(
        symbol='AAPL',
        current_price=175.50,
        sentiment_data=sentiment_data,
        quant_data=quant_data,
        portfolio_value=4500,
        current_position=None
    )

    print(f"Symbol: {rec['symbol']}")
    print(f"Action: {rec['action']}")
    print(f"Signal Strength: {rec['signal_strength']:.2f}")
    print(f"\nOrder Details:")
    print(f"  Type: {rec['order_type']}")
    print(f"  Current Price: ${rec['current_price']:.2f}")
    print(f"  Limit Price: ${rec['limit_price']:.2f}")
    print(f"  Shares: {rec['shares']}")
    print(f"  Order Value: ${rec['order_value']:.2f}")
    print(f"\nRationale: {rec['rationale']}")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    test_recommendation_engine()
