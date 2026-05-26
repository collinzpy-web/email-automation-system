# Email Automation System

Sends personalized emails using SMTP. Handles failures. Rotates servers. Logs everything.

## ⚠️ Important disclaimer

This tool is for **legitimate business email automation only** (newsletters, customer updates, follow-ups with consent).

You must comply with:
- **CAN-SPAM Act** (US) - include unsubscribe links, identify as business
- **GDPR** (EU) - have consent, allow data deletion
- **Your email provider's terms of service** (Gmail, Outlook, etc.)

**I do not support or condone spam.** If you use this for unsolicited emails, that's on you.

## Why I built this

A freelance marketer was sending 500+ follow-up emails manually every week. They were spending 15+ hours on repetitive copy-paste work. This system cut that to zero.

## What it does

- Sends personalized HTML emails with variable replacement
- Rotates through multiple SMTP servers (round-robin)
- Retries failed sends (up to 3 times per email)
- Logs every send to CSV (success/fail)
- Respects delay between emails (avoid rate limits)
- Dry run mode for testing
- Threaded sending (configurable concurrency)
- Marks dead SMTP servers after repeated failures

## Quick start

### 1. Install dependencies

**No external dependencies needed** — uses Python standard library only.

```bash
# Python 3.6+ required
python --version


email-automation-system/
├── email_automator.py       # Main script
├── config.json              # Your config 
├── smtp_credentials.txt     # Your SMTPs 
├── recipients.csv           # Your recipients 
├── template.html            # Your template 
├── send_log.csv             # Generated log 
├── error_log.txt            # Generated errors
├── email_system.log         # System logs
└── README.md                # This file
