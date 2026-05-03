#!/usr/bin/env python3
"""
Quantitative Analysis Engine - Simplified Version
Technical indicators using yfinance (free, no API key needed)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List
import yfinance as yf
import pandas as pd
import config

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class QuantEngine:
    """Performs technical analysis on stocks"""

    def __init__(self):
        pass

    def get_price_data(self, symbol: str, period: str = "3mo") -> pd.DataFrame:
        """
        Fetch historical price data
        period: '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', 'max'
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            logger.info(f"Fetched {len(data)} days of data for {symbol}")
            return data
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def calculate_rsi(self, data: pd.DataFrame, window: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(data) < window:
            return 50.0  # Neutral

        # Calculate price changes
        delta = data['Close'].diff()

        # Separate gains and losses
        gains = delta.where(delta > 0, 0)
        losses = -delta.where(delta < 0, 0)

        # Calculate average gains and losses
        avg_gains = gains.rolling(window=window).mean()
        avg_losses = losses.rolling(window=window).mean()

        # Calculate RS and RSI
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1] if not rsi.empty else 50.0

    def calculate_macd(self, data: pd.DataFrame) -> Dict:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(data) < 26:
            return {'macd': 0, 'signal': 0, 'histogram': 0, 'trend': 'NEUTRAL'}

        # Calculate EMAs
        ema_12 = data['Close'].ewm(span=12, adjust=False).mean()
        ema_26 = data['Close'].ewm(span=26, adjust=False).mean()

        # MACD line
        macd_line = ema_12 - ema_26

        # Signal line (9-day EMA of MACD)
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Histogram
        histogram = macd_line - signal_line

        # Determine trend
        if histogram.iloc[-1] > 0:
            trend = 'BULLISH' if histogram.iloc[-1] > histogram.iloc[-2] else 'WEAKENING_BULLISH'
        else:
            trend = 'BEARISH' if histogram.iloc[-1] < histogram.iloc[-2] else 'WEAKENING_BEARISH'

        return {
            'macd': macd_line.iloc[-1],
            'signal': signal_line.iloc[-1],
            'histogram': histogram.iloc[-1],
            'trend': trend
        }

    def calculate_moving_averages(self, data: pd.DataFrame) -> Dict:
        """Calculate key moving averages"""
        if len(data) < 200:
            logger.warning("Insufficient data for 200-day MA")

        mas = {}

        if len(data) >= 50:
            mas['sma_50'] = data['Close'].rolling(window=50).mean().iloc[-1]
            mas['current_vs_sma_50'] = ((data['Close'].iloc[-1] / mas['sma_50']) - 1) * 100

        if len(data) >= 200:
            mas['sma_200'] = data['Close'].rolling(window=200).mean().iloc[-1]
            mas['current_vs_sma_200'] = ((data['Close'].iloc[-1] / mas['sma_200']) - 1) * 100

            # Golden Cross / Death Cross
            if len(data) >= 200:
                sma_50 = data['Close'].rolling(window=50).mean()
                sma_200 = data['Close'].rolling(window=200).mean()

                if sma_50.iloc[-1] > sma_200.iloc[-1] and sma_50.iloc[-2] <= sma_200.iloc[-2]:
                    mas['cross'] = 'GOLDEN_CROSS'
                elif sma_50.iloc[-1] < sma_200.iloc[-1] and sma_50.iloc[-2] >= sma_200.iloc[-2]:
                    mas['cross'] = 'DEATH_CROSS'
                else:
                    mas['cross'] = 'NONE'

        return mas

    def analyze_volume(self, data: pd.DataFrame) -> Dict:
        """Analyze volume trends"""
        if len(data) < 20:
            return {'trend': 'INSUFFICIENT_DATA'}

        # Average volume (20-day)
        avg_volume = data['Volume'].rolling(window=20).mean().iloc[-1]
        current_volume = data['Volume'].iloc[-1]

        volume_ratio = current_volume / avg_volume

        if volume_ratio > 1.5:
            trend = 'HIGH_VOLUME'
        elif volume_ratio < 0.5:
            trend = 'LOW_VOLUME'
        else:
            trend = 'NORMAL_VOLUME'

        return {
            'current_volume': current_volume,
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'trend': trend
        }

    def find_support_resistance(self, data: pd.DataFrame) -> Dict:
        """Find key support and resistance levels (simplified)"""
        if len(data) < 20:
            return {}

        # Recent high/low
        recent_high = data['High'].tail(20).max()
        recent_low = data['Low'].tail(20).min()

        current_price = data['Close'].iloc[-1]

        # Distance to levels
        resistance_distance = ((recent_high / current_price) - 1) * 100
        support_distance = ((current_price / recent_low) - 1) * 100

        return {
            'resistance': recent_high,
            'support': recent_low,
            'current_price': current_price,
            'distance_to_resistance': resistance_distance,
            'distance_to_support': support_distance
        }

    def analyze_stock(self, symbol: str) -> Dict:
        """
        Complete technical analysis for a stock
        Returns all indicators and an overall signal strength
        """
        data = self.get_price_data(symbol, period="6mo")

        if data.empty or len(data) < 20:
            logger.warning(f"Insufficient data for {symbol}")
            return {
                'symbol': symbol,
                'error': 'Insufficient data',
                'signal_strength': 0.5,  # Neutral
                'recommendation': 'HOLD'
            }

        # Calculate all indicators
        rsi = self.calculate_rsi(data)
        macd = self.calculate_macd(data)
        mas = self.calculate_moving_averages(data)
        volume = self.analyze_volume(data)
        levels = self.find_support_resistance(data)

        # Calculate signal strength (0.0 to 1.0)
        # 0.0 = Strong Sell, 0.5 = Neutral, 1.0 = Strong Buy
        signals = []

        # RSI signal
        if rsi < config.RSI_OVERSOLD:
            signals.append(0.8)  # Oversold = bullish
        elif rsi > config.RSI_OVERBOUGHT:
            signals.append(0.2)  # Overbought = bearish
        else:
            signals.append(0.5)  # Neutral

        # MACD signal
        if macd['trend'] in ['BULLISH', 'WEAKENING_BEARISH']:
            signals.append(0.7)
        elif macd['trend'] in ['BEARISH', 'WEAKENING_BULLISH']:
            signals.append(0.3)
        else:
            signals.append(0.5)

        # Moving Average signal
        if 'current_vs_sma_50' in mas:
            if mas['current_vs_sma_50'] > 5:
                signals.append(0.7)  # Well above MA
            elif mas['current_vs_sma_50'] < -5:
                signals.append(0.3)  # Well below MA
            else:
                signals.append(0.5)

        # Average all signals
        overall_signal = sum(signals) / len(signals)

        # Determine recommendation
        if overall_signal >= config.STRONG_BUY_THRESHOLD:
            recommendation = 'STRONG_BUY'
        elif overall_signal >= config.BUY_THRESHOLD:
            recommendation = 'BUY'
        elif overall_signal >= config.HOLD_THRESHOLD:
            recommendation = 'HOLD'
        elif overall_signal >= config.SELL_THRESHOLD:
            recommendation = 'WEAK_SELL'
        else:
            recommendation = 'STRONG_SELL'

        return {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'signal_strength': overall_signal,
            'recommendation': recommendation,
            'indicators': {
                'rsi': rsi,
                'macd': macd,
                'moving_averages': mas,
                'volume': volume,
                'support_resistance': levels
            }
        }

    def analyze_multiple_stocks(self, symbols: List[str]) -> Dict[str, Dict]:
        """Analyze multiple stocks"""
        results = {}

        for symbol in symbols:
            try:
                analysis = self.analyze_stock(symbol)
                results[symbol] = analysis
                logger.info(f"{symbol}: {analysis['recommendation']} (signal: {analysis['signal_strength']:.2f})")
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")

        return results


def test_quant_engine():
    """Test the quant engine"""
    print("\n" + "="*60)
    print("  QUANTITATIVE ANALYSIS TEST")
    print("="*60 + "\n")

    engine = QuantEngine()

    test_symbols = ['AAPL', 'NVDA']

    for symbol in test_symbols:
        print(f"\nAnalyzing {symbol}...")
        print("-" * 40)

        analysis = engine.analyze_stock(symbol)

        if 'error' in analysis:
            print(f"Error: {analysis['error']}")
            continue

        print(f"Recommendation: {analysis['recommendation']}")
        print(f"Signal Strength: {analysis['signal_strength']:.2f}")
        print(f"\nIndicators:")
        print(f"  RSI: {analysis['indicators']['rsi']:.1f}")
        print(f"  MACD Trend: {analysis['indicators']['macd']['trend']}")

        if 'current_vs_sma_50' in analysis['indicators']['moving_averages']:
            print(f"  vs 50-day MA: {analysis['indicators']['moving_averages']['current_vs_sma_50']:+.1f}%")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    test_quant_engine()
