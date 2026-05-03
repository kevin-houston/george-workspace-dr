#!/usr/bin/env python3
"""
Daily Scheduler - Integrates with nanoclaw scheduler
Runs advisor at 8 AM daily and emails results
"""

import sys
from datetime import datetime
from advisor import RobinhoodAdvisor
import config

def run_daily_report():
    """
    Main function to run daily analysis
    This will be called by nanoclaw scheduler
    """
    print(f"\n{'='*60}")
    print(f"  ROBINHOOD DAILY ANALYSIS")
    print(f"  {datetime.now().strftime('%B %d, %Y at %H:%M')}")
    print(f"{'='*60}\n")

    try:
        # Create advisor
        advisor = RobinhoodAdvisor()

        # Run analysis with live Robinhood data; falls back to CSV if login fails
        print("Running portfolio analysis (live Robinhood data)...")
        results = advisor.run_daily_analysis(use_robinhood=True)

        # Generate report
        print("Generating report...")
        report_text = advisor.format_text_report(results)

        # Save report
        report_file = config.DATA_DIR / f"daily_report_{datetime.now().strftime('%Y%m%d')}.txt"
        with open(report_file, 'w') as f:
            f.write(report_text)

        print(f"✅ Report saved to: {report_file}")

        # Output report (this will be captured by nanoclaw and emailed)
        print("\n" + "="*60)
        print("  EMAIL CONTENT")
        print("="*60 + "\n")
        print(report_text)

        print("\n" + "="*60)
        print("  Daily analysis complete!")
        print("="*60 + "\n")

        # Return success
        return 0

    except Exception as e:
        print(f"\n❌ Error running daily analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = run_daily_report()
    sys.exit(exit_code)
