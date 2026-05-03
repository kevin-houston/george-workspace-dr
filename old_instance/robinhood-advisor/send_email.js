#!/usr/bin/env node
/**
 * Send email report using nodemailer
 */

const nodemailer = require('nodemailer');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

async function sendEmail() {
  // Email configuration from .env
  const fromEmail = process.env.EMAIL_FROM || 'kevindothouston@gmail.com';
  const toEmail = process.env.EMAIL_TO || 'kevinclaw26@gmail.com';
  const appPassword = process.env.GMAIL_APP_PASSWORD;

  if (!appPassword) {
    console.error('❌ ERROR: GMAIL_APP_PASSWORD not set in .env file');
    console.error('\nTo set up Gmail app password:');
    console.error('1. Go to https://myaccount.google.com/apppasswords');
    console.error('2. Generate a new app password for "Mail"');
    console.error('3. Add to .env file: GMAIL_APP_PASSWORD=your_16_char_password');
    process.exit(1);
  }

  // Read the report file
  const reportFile = process.argv[2] ||
    path.join(__dirname, 'data', `daily_report_${new Date().toISOString().split('T')[0].replace(/-/g, '')}.txt`);

  if (!fs.existsSync(reportFile)) {
    console.error(`❌ ERROR: Report file not found: ${reportFile}`);
    process.exit(1);
  }

  const reportContent = fs.readFileSync(reportFile, 'utf8');

  // Create email subject
  const today = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
  const subject = `📊 Daily Portfolio Analysis - ${today}`;

  // Create transporter
  const transporter = nodemailer.createTransport({
    service: 'gmail',
    auth: {
      user: fromEmail,
      pass: appPassword
    }
  });

  // Email options
  const mailOptions = {
    from: fromEmail,
    to: toEmail,
    subject: subject,
    text: reportContent
  };

  try {
    console.log(`Sending email to ${toEmail}...`);
    const info = await transporter.sendMail(mailOptions);
    console.log(`✅ Email sent successfully!`);
    console.log(`📧 Message ID: ${info.messageId}`);
    console.log(`📁 Report file: ${reportFile}`);
    return true;
  } catch (error) {
    console.error(`❌ Error sending email: ${error.message}`);
    return false;
  }
}

sendEmail().then(success => {
  process.exit(success ? 0 : 1);
});
