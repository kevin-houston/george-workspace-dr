#!/usr/bin/env python3
"""
Email sender for portfolio reports
Requires Gmail app password in .env file
"""
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

def send_gmail(subject, body, to_email, from_email, app_password):
    """Send email via Gmail SMTP using app password"""

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        print(f"Connecting to Gmail SMTP server...")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()

        print(f"Logging in as {from_email}...")
        server.login(from_email, app_password)

        print(f"Sending email to {to_email}...")
        server.send_message(msg)
        server.quit()

        print(f"✅ Email sent successfully!")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

def main():
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    # Get email configuration
    from_email = os.getenv('EMAIL_FROM', 'kevindothouston@gmail.com')
    to_email = os.getenv('EMAIL_TO', 'kevinclaw26@gmail.com')
    app_password = os.getenv('GMAIL_APP_PASSWORD')

    if not app_password:
        print("❌ ERROR: GMAIL_APP_PASSWORD not set in .env file")
        print("\nTo set up Gmail app password:")
        print("1. Go to https://myaccount.google.com/apppasswords")
        print("2. Generate a new app password for 'Mail'")
        print("3. Add to .env file: GMAIL_APP_PASSWORD=your_16_char_password")
        print("\nFor now, email content is shown below:")
        print("="*60)

        # Read and display the report
        report_file = sys.argv[1] if len(sys.argv) > 1 else None
        if not report_file:
            # Find most recent report
            data_dir = Path(__file__).parent / 'data'
            reports = sorted(data_dir.glob('daily_report_*.txt'), reverse=True)
            report_file = reports[0] if reports else None

        if report_file:
            with open(report_file, 'r') as f:
                print(f.read())

        return False

    # Find report file
    report_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not report_file:
        # Find most recent report
        data_dir = Path(__file__).parent / 'data'
        reports = sorted(data_dir.glob('daily_report_*.txt'), reverse=True)
        report_file = reports[0] if reports else None

    if not report_file or not Path(report_file).exists():
        print(f"❌ ERROR: Report file not found: {report_file}")
        return False

    # Read report content
    with open(report_file, 'r') as f:
        report_content = f.read()

    # Create subject line
    today = datetime.now().strftime("%B %d, %Y")
    subject = f"📊 Daily Portfolio Analysis - {today}"

    # Send email
    success = send_gmail(subject, report_content, to_email, from_email, app_password)

    if success:
        print(f"\n📧 Report emailed to {to_email}")
        print(f"📁 Report also saved to: {report_file}")

    return success

if __name__ == "__main__":
    main()
