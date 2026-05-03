# Email Setup for Portfolio Reports

## Current Status

The portfolio advisor generates daily reports but email sending is not yet configured. Reports are currently delivered via WhatsApp.

## How to Enable Email Delivery

### Step 1: Create Gmail App Password

1. Go to https://myaccount.google.com/apppasswords
2. Sign in with your Google account (kevindothouston@gmail.com)
3. Click "Select app" → Choose "Mail"
4. Click "Select device" → Choose "Other (Custom name)"
5. Enter name: "Portfolio Advisor"
6. Click "Generate"
7. Copy the 16-character password (format: xxxx xxxx xxxx xxxx)

### Step 2: Add App Password to .env

Edit `/workspace/group/robinhood-advisor/.env` and add:

```
GMAIL_APP_PASSWORD=your16charpassword
EMAIL_FROM=kevindothouston@gmail.com
EMAIL_TO=kevinclaw26@gmail.com
```

### Step 3: Install Python Email Dependencies

The email script requires Python's `smtplib` (built-in) and `python-dotenv`:

```bash
cd /workspace/group/robinhood-advisor
pip install python-dotenv
```

### Step 4: Test Email Sending

```bash
python3 send_email_report.py
```

This will:
- Read the most recent daily report from `data/`
- Send it via Gmail SMTP to kevinclaw26@gmail.com
- Display success/failure message

## Alternative: Use SendGrid API

If Gmail app passwords don't work, you can use SendGrid (free tier: 100 emails/day):

1. Sign up at https://sendgrid.com
2. Create API key
3. Add to .env: `SENDGRID_API_KEY=your_api_key`
4. Install: `pip install sendgrid`

## Automated Daily Emails

Once email is working, the scheduled task will automatically email reports daily at 8 AM.

Current scheduled task (from nanoclaw):
```
Runs at 8:00 AM daily
Executes: advisor.py → generates report → send_email_report.py → emails to kevinclaw26@gmail.com
```

## Troubleshooting

### "GMAIL_APP_PASSWORD not set"
- Check .env file exists and has the password
- Make sure no spaces around the = sign
- Password should be 16 characters (no spaces)

### "Authentication failed"
- Double-check the app password is correct
- Make sure 2FA is enabled on your Google account
- Try generating a new app password

### "Connection refused"
- Check internet connectivity
- Gmail SMTP may be blocked by firewall
- Try using port 465 (SSL) instead of 587 (TLS)

## Current Workaround

Until email is configured, reports are:
1. Saved to `data/daily_report_YYYYMMDD.txt`
2. Summary sent via WhatsApp through nanoclaw
3. Full report available in the data folder

## Future Enhancements

- HTML email formatting with charts
- Attachment: CSV export of trades
- Mobile-optimized email template
- Weekly/monthly summary emails
