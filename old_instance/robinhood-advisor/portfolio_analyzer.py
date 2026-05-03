#!/usr/bin/env python3
"""
Portfolio Analyzer - Connects to Robinhood and fetches portfolio data
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import robin_stocks.robinhood as rh
import config

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class PortfolioAnalyzer:
    """Manages connection to Robinhood and portfolio analysis"""

    def __init__(self):
        self.logged_in = False
        self.portfolio_data = None
        self.positions = []

    def login(self, username: str = None, password: str = None, mfa_code: str = None):
        """Login to Robinhood. Uses persistent session token to avoid repeated MFA prompts."""
        username = username or config.ROBINHOOD_USERNAME
        password = password or config.ROBINHOOD_PASSWORD
        mfa_code = mfa_code or config.ROBINHOOD_MFA_CODE

        # Store session pickle in persistent data dir so it survives container restarts
        persistent_pickle_dir = str(config.DATA_DIR)

        try:
            if mfa_code:
                login = rh.login(username, password, mfa_code=mfa_code,
                                 pickle_path=persistent_pickle_dir)
            else:
                login = rh.login(username, password,
                                 pickle_path=persistent_pickle_dir)

            self.logged_in = True
            logger.info("Successfully logged into Robinhood")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            self.logged_in = False
            return False

    def logout(self):
        """Logout from Robinhood"""
        try:
            rh.logout()
            self.logged_in = False
            logger.info("Logged out from Robinhood")
        except Exception as e:
            logger.error(f"Logout error: {e}")

    def get_portfolio_value(self) -> float:
        """Get total portfolio value"""
        if not self.logged_in:
            logger.warning("Not logged in")
            return 0.0

        try:
            profile = rh.profiles.load_portfolio_profile()
            equity = float(profile['equity'])
            logger.info(f"Portfolio equity: ${equity:,.2f}")
            return equity
        except Exception as e:
            logger.error(f"Error fetching portfolio value: {e}")
            return 0.0

    def get_positions(self) -> List[Dict]:
        """Get all current stock positions"""
        if not self.logged_in:
            logger.warning("Not logged in")
            return []

        try:
            positions = rh.account.build_holdings()

            formatted_positions = []
            for symbol, data in positions.items():
                position = {
                    'symbol': symbol,
                    'quantity': float(data['quantity']),
                    'avg_buy_price': float(data['average_buy_price']),
                    'current_price': float(data['price']),
                    'equity': float(data['equity']),
                    'percent_change': float(data['percent_change']),
                    'equity_change': float(data['equity_change']),
                    'type': data['type'],
                }

                # Calculate additional metrics
                position['total_cost'] = position['quantity'] * position['avg_buy_price']
                position['total_return'] = position['equity'] - position['total_cost']
                position['total_return_pct'] = (position['total_return'] / position['total_cost']) * 100
                position['portfolio_weight'] = 0  # Will calculate after we have total

                formatted_positions.append(position)

            # Calculate portfolio weights
            total_equity = sum(p['equity'] for p in formatted_positions)
            for position in formatted_positions:
                position['portfolio_weight'] = (position['equity'] / total_equity) * 100

            self.positions = formatted_positions
            logger.info(f"Fetched {len(formatted_positions)} positions")
            return formatted_positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_historical_portfolio(self, span: str = "month") -> List[Dict]:
        """
        Get historical portfolio performance
        span: 'day', 'week', 'month', 'year', '5year', 'all'
        """
        if not self.logged_in:
            return []

        try:
            historicals = rh.account.get_historical_portfolio(span=span)
            return historicals
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return []

    def get_cash_balance(self) -> float:
        """Get available cash balance"""
        if not self.logged_in:
            return 0.0

        try:
            profile = rh.profiles.load_portfolio_profile()
            cash = float(profile.get('withdrawable_amount', 0))
            logger.info(f"Available cash: ${cash:,.2f}")
            return cash
        except Exception as e:
            logger.error(f"Error fetching cash balance: {e}")
            return 0.0

    def get_dividends(self) -> List[Dict]:
        """Get dividend information"""
        if not self.logged_in:
            return []

        try:
            dividends = rh.account.get_dividends()
            return dividends
        except Exception as e:
            logger.error(f"Error fetching dividends: {e}")
            return []

    def save_portfolio_snapshot(self):
        """Save current portfolio state to file"""
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'total_equity': self.get_portfolio_value(),
            'cash': self.get_cash_balance(),
            'positions': self.positions,
            'num_positions': len(self.positions)
        }

        # Load existing history
        history = []
        if config.HISTORY_FILE.exists():
            with open(config.HISTORY_FILE, 'r') as f:
                history = json.load(f)

        # Append new snapshot
        history.append(snapshot)

        # Keep last 90 days
        if len(history) > 90:
            history = history[-90:]

        # Save
        with open(config.HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)

        logger.info("Portfolio snapshot saved")

    def get_portfolio_summary(self) -> Dict:
        """Get comprehensive portfolio summary"""
        if not self.logged_in:
            return {}

        total_equity = self.get_portfolio_value()
        cash = self.get_cash_balance()
        positions = self.get_positions()

        # Calculate summary stats
        total_invested = sum(p['total_cost'] for p in positions)
        total_return = sum(p['total_return'] for p in positions)
        total_return_pct = (total_return / total_invested * 100) if total_invested > 0 else 0

        # Find best/worst performers
        if positions:
            best_performer = max(positions, key=lambda x: x['total_return_pct'])
            worst_performer = min(positions, key=lambda x: x['total_return_pct'])
        else:
            best_performer = worst_performer = None

        summary = {
            'total_equity': total_equity,
            'cash': cash,
            'invested': total_invested,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'num_positions': len(positions),
            'positions': positions,
            'best_performer': best_performer,
            'worst_performer': worst_performer,
            'timestamp': datetime.now().isoformat()
        }

        return summary

    def check_rebalance_needed(self) -> List[Dict]:
        """Check if any positions need rebalancing"""
        positions = self.get_positions()
        rebalance_recommendations = []

        target_weight = 100 / config.NUM_HOLDINGS  # Equal weight

        for position in positions:
            weight_diff = position['portfolio_weight'] - target_weight

            if abs(weight_diff) > config.REBALANCE_THRESHOLD * 100:
                action = "REDUCE" if weight_diff > 0 else "INCREASE"
                rebalance_recommendations.append({
                    'symbol': position['symbol'],
                    'current_weight': position['portfolio_weight'],
                    'target_weight': target_weight,
                    'difference': weight_diff,
                    'action': action,
                    'reason': f"Position drifted {abs(weight_diff):.1f}% from target"
                })

        return rebalance_recommendations


def test_analyzer():
    """Test the portfolio analyzer"""
    print("\n" + "="*60)
    print("  PORTFOLIO ANALYZER TEST")
    print("="*60 + "\n")

    analyzer = PortfolioAnalyzer()

    print("Note: This test requires Robinhood credentials")
    print("Set ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD in .env file\n")

    # For testing without login
    print("Analyzer initialized successfully")
    print("\nTo use with real account:")
    print("1. Set credentials in .env")
    print("2. Run: analyzer.login()")
    print("3. Run: analyzer.get_portfolio_summary()")


if __name__ == "__main__":
    test_analyzer()
