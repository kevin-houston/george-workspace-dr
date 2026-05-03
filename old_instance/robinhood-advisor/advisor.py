#!/usr/bin/env python3
"""
Robinhood Advisor - Main Orchestrator (Simplified Version)
Combines all engines and generates daily report
"""

import json
import logging
from datetime import datetime
from typing import Dict, List
import numpy as np
import config
from portfolio_analyzer import PortfolioAnalyzer
from csv_portfolio import CSVPortfolio
from sentiment_engine import SentimentEngine
from quant_engine import QuantEngine
from recommendation_engine import RecommendationEngine

logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class RobinhoodAdvisor:
    """Main advisor that orchestrates all analysis"""

    def __init__(self):
        self.portfolio = PortfolioAnalyzer()
        self.csv_portfolio = CSVPortfolio()
        self.sentiment = SentimentEngine()
        self.quant = QuantEngine()
        self.recommender = RecommendationEngine()

    def run_daily_analysis(self, use_csv: bool = False, use_robinhood: bool = True) -> Dict:
        """
        Run complete daily analysis
        use_csv: Load portfolio from CSV file (recommended, no login needed)
        use_robinhood: Connect to Robinhood API (requires credentials)
        Returns: Full analysis results
        """
        logger.info("Starting daily analysis...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'portfolio_summary': {},
            'recommendations': [],
            'performance': {}
        }

        # Step 1: Get portfolio
        positions = []  # Initialize positions for all paths

        if use_robinhood and self.portfolio.login():
            logger.info("Loading live portfolio from Robinhood...")
            portfolio_summary = self.portfolio.get_portfolio_summary()
            positions = portfolio_summary['positions']
            portfolio_value = portfolio_summary['total_equity']

            results['portfolio_summary'] = portfolio_summary

            # Get symbols from positions
            symbols = [p['symbol'] for p in positions]

        elif use_csv or True:  # Fall back to CSV if Robinhood fails
            if use_robinhood:
                logger.warning("Robinhood login failed — falling back to CSV portfolio")
            else:
                logger.info("Loading portfolio from CSV file...")
            symbols = self.csv_portfolio.load_portfolio()
            positions = self.csv_portfolio.get_positions()
            portfolio_value = config.PORTFOLIO_SIZE

            results['portfolio_summary'] = {
                'total_equity': portfolio_value,
                'num_positions': len(symbols),
                'source': 'CSV file (Robinhood login failed — update portfolio.csv if holdings have changed)'
            }

        else:
            # Mock portfolio for testing
            logger.info("Using mock portfolio data")
            symbols = ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL']
            portfolio_value = config.PORTFOLIO_SIZE
            positions = []

            results['portfolio_summary'] = {
                'total_equity': portfolio_value,
                'num_positions': len(symbols),
                'mock_data': True
            }

        # Step 2: Analyze each stock
        logger.info(f"Analyzing {len(symbols)} stocks...")

        all_recommendations = []

        for symbol in symbols:
            try:
                logger.info(f"Analyzing {symbol}...")

                # Get sentiment
                sentiment_data = self.sentiment.analyze_stock_sentiment(symbol)

                # Get technical analysis
                quant_data = self.quant.analyze_stock(symbol)

                # Find current position
                current_position = None
                if positions:
                    current_position = next((p for p in positions if p['symbol'] == symbol), None)

                current_price = quant_data['indicators']['support_resistance']['current_price'] \
                    if 'indicators' in quant_data and 'support_resistance' in quant_data['indicators'] \
                    else 0

                # Generate recommendation
                recommendation = self.recommender.generate_recommendation(
                    symbol=symbol,
                    current_price=current_price,
                    sentiment_data=sentiment_data,
                    quant_data=quant_data,
                    portfolio_value=portfolio_value,
                    current_position=current_position
                )

                all_recommendations.append(recommendation)

            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")

        # Step 3: Filter to actionable recommendations
        actionable = self.recommender.filter_actionable_recommendations(
            all_recommendations,
            max_trades=config.MAX_DAILY_TRADES
        )

        # Step 4: Categorize
        categorized = self.recommender.categorize_recommendations(all_recommendations)

        results['recommendations'] = all_recommendations
        results['actionable'] = actionable
        results['categorized'] = categorized

        logger.info(f"Analysis complete: {len(actionable)} actionable recommendations")

        # Save results
        self.save_results(results)

        return results

    def save_results(self, results: Dict):
        """Save analysis results to file"""
        filename = config.DATA_DIR / f"analysis_{datetime.now().strftime('%Y%m%d')}.json"

        # Convert numpy types to native Python types for JSON serialization
        def convert_types(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            return obj

        results_converted = convert_types(results)

        with open(filename, 'w') as f:
            json.dump(results_converted, f, indent=2)

        logger.info(f"Results saved to {filename}")

    def format_text_report(self, results: Dict) -> str:
        """
        Format results as plain text report
        This will be sent via email
        """
        report_lines = []

        # Header
        report_lines.append("="*60)
        report_lines.append("  PORTFOLIO MORNING BRIEF")
        report_lines.append(f"  {datetime.now().strftime('%B %d, %Y')}")
        report_lines.append("="*60)
        report_lines.append("")

        # Portfolio Summary
        summary = results['portfolio_summary']
        report_lines.append(f"Portfolio Value: ${summary.get('total_equity', 0):,.2f}")

        if 'total_return_pct' in summary:
            report_lines.append(f"Total Return: {summary['total_return_pct']:+.2f}%")

        report_lines.append(f"Positions: {summary.get('num_positions', 0)}")
        report_lines.append("")

        # Actionable Recommendations
        actionable = results.get('actionable', [])

        if actionable:
            report_lines.append("="*60)
            report_lines.append(f"  🎯 TODAY'S RECOMMENDATIONS ({len(actionable)} orders)")
            report_lines.append("="*60)
            report_lines.append("")

            for i, rec in enumerate(actionable, 1):
                symbol = rec['symbol']
                action = rec['action']
                order_type = rec['order_type']
                emoji = "🟢" if order_type in ['BUY', 'MARKET_BUY'] else "🔴"

                # Format shares - show 2 decimals if fractional, otherwise integer
                shares_display = f"{rec['shares']:.2f}" if rec['shares'] < 1 or rec['shares'] % 1 != 0 else f"{int(rec['shares'])}"

                report_lines.append(f"{emoji} {i}. {symbol} - {action}")
                report_lines.append(f"   Current: ${rec['current_price']:.2f}")

                # Format order line based on type
                if order_type == 'MARKET_SELL':
                    report_lines.append(f"   → Market Sell: ~${rec['limit_price']:.2f} ({shares_display} shares)")
                    report_lines.append(f"   Note: Fractional shares require market orders on Robinhood")
                else:
                    report_lines.append(f"   → Limit {order_type}: ${rec['limit_price']:.2f} ({shares_display} shares)")

                report_lines.append(f"   Order Value: ${rec['order_value']:.2f}")
                report_lines.append(f"   Signal: {rec['signal_strength']:.0%}")
                report_lines.append(f"   Rationale: {rec['rationale']}")
                report_lines.append("")

        else:
            report_lines.append("📭 No actionable recommendations today")
            report_lines.append("")

        # Hold Positions
        categorized = results.get('categorized', {})
        holds = categorized.get('hold', [])

        if holds:
            report_lines.append("="*60)
            report_lines.append(f"  ⚪ HOLD ({len(holds)} positions)")
            report_lines.append("="*60)
            report_lines.append("")

            for rec in holds[:5]:  # Show top 5
                symbol = rec['symbol']
                current_return = rec['current_position']['current_return_pct']
                report_lines.append(f"  {symbol}: ${rec['current_price']:.2f} ({current_return:+.1f}%)")

            report_lines.append("")

        # Footer
        report_lines.append("="*60)
        report_lines.append("")
        report_lines.append("This is an automated analysis. Always do your own research.")
        report_lines.append("Generated by Robinhood Advisor")
        report_lines.append("")

        return "\n".join(report_lines)

    def send_email_report(self, results: Dict):
        """Send email report using mcp__nanoclaw__send_message"""
        report_text = self.format_text_report(results)

        # For nanoclaw, we'll save to a file that can be emailed
        # Or use the send_message tool if available

        report_file = config.DATA_DIR / f"daily_report_{datetime.now().strftime('%Y%m%d')}.txt"

        with open(report_file, 'w') as f:
            f.write(report_text)

        logger.info(f"Report saved to {report_file}")

        # Print to console for now
        print("\n" + report_text)

        return report_text


def test_advisor():
    """Test the advisor with mock data"""
    print("\n" + "="*60)
    print("  ROBINHOOD ADVISOR TEST")
    print("="*60 + "\n")

    advisor = RobinhoodAdvisor()

    print("Running analysis with mock data...")
    print("(Set use_robinhood=True to use real portfolio)\n")

    # Run analysis
    results = advisor.run_daily_analysis(use_robinhood=False)

    # Generate and display report
    print("\n" + "="*60)
    print("  GENERATED REPORT")
    print("="*60 + "\n")

    report = advisor.send_email_report(results)

    print("\n" + "="*60)
    print(f"  Analysis complete!")
    print(f"  Analyzed {len(results['recommendations'])} stocks")
    print(f"  Found {len(results['actionable'])} actionable recommendations")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_advisor()
