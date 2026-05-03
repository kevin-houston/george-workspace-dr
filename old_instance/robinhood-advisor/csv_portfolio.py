#!/usr/bin/env python3
"""
CSV Portfolio Loader - Reads portfolio from CSV file
No Robinhood login required!
"""

import csv
import logging
from pathlib import Path
from typing import List, Dict
import config

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class CSVPortfolio:
    """Loads portfolio from CSV file"""

    def __init__(self, csv_path: str = None):
        self.csv_path = csv_path or (config.DATA_DIR / "portfolio.csv")
        self.positions = []

    def load_portfolio(self) -> List[str]:
        """
        Load portfolio from CSV
        Returns: List of stock symbols
        """
        if not Path(self.csv_path).exists():
            logger.error(f"Portfolio file not found: {self.csv_path}")
            logger.info("Creating sample portfolio.csv...")
            self._create_sample_csv()
            return []

        symbols = []
        positions = []

        try:
            with open(self.csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row['symbol'].strip().upper()
                    shares = float(row.get('shares', 0))
                    avg_cost = float(row.get('avg_cost', 0))

                    symbols.append(symbol)
                    positions.append({
                        'symbol': symbol,
                        'quantity': shares,  # Match recommendation_engine.py expectations
                        'avg_buy_price': avg_cost  # Match recommendation_engine.py expectations
                    })

            self.positions = positions
            logger.info(f"Loaded {len(symbols)} stocks from CSV: {symbols}")
            return symbols

        except Exception as e:
            logger.error(f"Error loading portfolio CSV: {e}")
            return []

    def get_positions(self) -> List[Dict]:
        """Get positions with current data"""
        return self.positions

    def _create_sample_csv(self):
        """Create a sample CSV file"""
        sample_data = [
            {'symbol': 'AAPL', 'shares': '10', 'avg_cost': '150.00'},
            {'symbol': 'NVDA', 'shares': '5', 'avg_cost': '120.00'},
            {'symbol': 'TSLA', 'shares': '8', 'avg_cost': '200.00'},
            {'symbol': 'MSFT', 'shares': '12', 'avg_cost': '300.00'},
            {'symbol': 'GOOGL', 'shares': '6', 'avg_cost': '100.00'},
        ]

        with open(self.csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['symbol', 'shares', 'avg_cost'])
            writer.writeheader()
            writer.writerows(sample_data)

        logger.info(f"Created sample portfolio at: {self.csv_path}")


if __name__ == "__main__":
    portfolio = CSVPortfolio()
    symbols = portfolio.load_portfolio()
    print(f"\nLoaded symbols: {symbols}")
    print(f"Positions: {portfolio.get_positions()}")
