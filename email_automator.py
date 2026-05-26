#!/usr/bin/env python3
"""
Email Automation System - Sends personalized emails with SMTP rotation.
No over-engineering. Just works.
"""

import sys
import os
import csv
import json
import time
import smtplib
import logging
import argparse
import threading
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_system.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global lock for thread-safe operations
log_lock = threading.Lock()
smtp_lock = threading.Lock()

# Global SMTP rotation index
smtp_index = 0

def load_config(config_path='config.json'):
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Validate required fields
    required = ['subject', 'sender_name', 'sender_email']
    for field in required:
        if field not in config:
            logger.error(f"Missing required config field: {field}")
            sys.exit(1)
    
    return config

def load_smtps(smtp_path='smtp_credentials.txt'):
    """Load SMTP servers from file. Format: host|port|username|password"""
    if not os.path.exists(smtp_path):
        logger.error(f"SMTP file not found: {smtp_path}")
        sys.exit(1)
    
    smtps = []
    with open(smtp_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('|')
            if len(parts) != 4:
                logger.warning(f"Line {line_num}: Invalid format (skipped): {line}")
                continue
            
            host, port, username, password = parts
            smtps.append({
                'host': host,
                'port': int(port),
                'username': username,
                'password': password,
                'failed': False
            })
    
    if not smtps:
        logger.error("No valid SMTP servers found")
        sys.exit(1)
    
    logger.info(f"Loaded {len(smtps)} SMTP servers")
    return smtps

def load_recipients(recipients_path='recipients.csv'):
    """Load recipients from CSV. Expects 'email' column, optional 'name' column."""
    if not os.path.exists(recipients_path):
        logger.error(f"Recipients file not found: {recipients_path}")
        sys.exit(1)
    
    recipients = []
    with open(recipients_path, 'r') as f:
        reader = csv.DictReader(f)
        
        if 'email' not in reader.fieldnames:
            logger.error("CSV must have an 'email' column")
            sys.exit(1)
        
        for row in reader:
            email = row.get('email', '').strip().lower()
            if email:
                recipients.append({
                    'email': email,
                    'name': row.get('name', '').strip()
                })
    
    if not recipients:
        logger.error("No valid recipients found")
        sys.exit(1)
    
    logger.info(f"Loaded {len(recipients)} recipients")
    return recipients

def load_template(template_path='template.html'):
    """Load HTML template from file."""
    if not os.path.exists(template_path):
        logger.error(f"Template file not found: {template_path}")
        sys.exit(1)
    
    with open(template_path, 'r') as f:
        template = f.read()
    
    return template

def rotate_smtp(smtps):
    """Get next SMTP server (round-robin)."""
    global smtp_index
    
    with smtp_lock:
        # Find next working SMTP
        for _ in range(len(smtps)):
            smtp = smtps[smtp_index % len(smtps)]
            smtp_index += 1
            
            if not smtp.get('failed', False):
                return smtp
        
        # All SMTPs failed
        return None

def test_smtp_connection(smtp):
    """Test SMTP connection and login."""
    try:
        if smtp['port'] == 465:
            server = smtplib.SMTP_SSL(smtp['host'], smtp['port'], timeout=10)
        else:
            server = smtplib.SMTP(smtp['host'], smtp['port'], timeout=10)
            server.starttls()
        
        server.login(smtp['username'], smtp['password'])
        server.quit()
        return True
    except Exception as e:
        logger.warning(f"SMTP test failed for {smtp['host']}: {str(e)}")
        return False

def personalize_template(template, recipient, config):
    """Replace template variables with actual values."""
    replacements = {
        '{{email}}': recipient['email'],
        '{{name}}': recipient['name'] if recipient['name'] else 'there',
        '{{current_date}}': datetime.now().strftime('%B %d, %Y'),
        '{{current_time}}': datetime.now().strftime('%I:%M %p'),
        '{{random_id}}': make_msgid()[1:-1][:8]  # first 8 chars of message-id
    }
    
    # Add any custom replacements from config
    if 'variables' in config:
        for key, value in config['variables'].items():
            replacements[f'{{{{{key}}}}}'] = value
    
    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value))
    
    return result

def send_email(recipient, smtp, config, template):
    """Send a single email using given SMTP server."""
    try:
        # Personalize content
        subject = personalize_template(config['subject'], recipient, config)
        html_body = personalize_template(template, recipient, config)
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr((config['sender_name'], config['sender_email']))
        msg['To'] = recipient['email']
        msg['Message-ID'] = make_msgid()
        
        # Attach HTML part
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send
        if smtp['port'] == 465:
            server = smtplib.SMTP_SSL(smtp['host'], smtp['port'], timeout=15)
        else:
            server = smtplib.SMTP(smtp['host'], smtp['port'], timeout=15)
            server.starttls()
        
        server.login(smtp['username'], smtp['password'])
        server.send_message(msg)
        server.quit()
        
        return True, None
    
    except smtplib.SMTPRecipientsRefused as e:
        return False, f"Recipient refused: {str(e)}"
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Auth failed: {str(e)}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Unknown error: {str(e)}"

def log_send(recipient_email, smtp_host, status, error_msg=''):
    """Log email send attempt to CSV."""
    with log_lock:
        file_exists = os.path.exists('send_log.csv')
        
        with open('send_log.csv', 'a', newline='') as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow(['timestamp', 'recipient', 'smtp', 'status', 'error'])
            
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                recipient_email,
                smtp_host,
                status,
                error_msg
            ])

def log_error(recipient_email, error_msg):
    """Log error to separate file."""
    with log_lock:
        with open('error_log.txt', 'a') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {recipient_email}: {error_msg}\n")

def process_recipient(recipient, smtps, config, template, max_retries):
    """Process single recipient with retries and SMTP rotation."""
    last_error = None
    
    for attempt in range(max_retries):
        smtp = rotate_smtp(smtps)
        if not smtp:
            error_msg = "No working SMTP servers available"
            log_error(recipient['email'], error_msg)
            log_send(recipient['email'], 'none', 'failed', error_msg)
            return False
        
        success, error = send_email(recipient, smtp, config, template)
        
        if success:
            logger.info(f"✓ Sent to {recipient['email']} via {smtp['host']}")
            log_send(recipient['email'], smtp['host'], 'sent')
            return True
        
        # Failed, log and retry
        last_error = error
        logger.warning(f"✗ Attempt {attempt+1}/{max_retries} failed for {recipient['email']}: {error}")
        
        if attempt < max_retries - 1:
            time.sleep(2)  # Wait before retry
            # Mark SMTP as failed only after it fails multiple times
            if attempt >= 1:
                with smtp_lock:
                    smtp['failed'] = True
                    logger.warning(f"Marked {smtp['host']} as failed")
    
    # All retries exhausted
    log_error(recipient['email'], last_error)
    log_send(recipient['email'], 'unknown', 'failed', last_error)
    logger.error(f"✗ Failed to send to {recipient['email']} after {max_retries} attempts")
    return False

def main():
    parser = argparse.ArgumentParser(description='Email Automation System')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no actual sends')
    parser.add_argument('--test', action='store_true', help='Send to first 5 recipients only')
    args = parser.parse_args()
    
    print("\n" + "=" * 50)
    print("EMAIL AUTOMATION SYSTEM")
    print("=" * 50 + "\n")
    
    # Load configuration
    config = load_config(args.config)
    
    # Override with command line flags
    if args.dry_run:
        config['dry_run'] = True
    
    # Load SMTPs and test them
    smtps = load_smtps()
    
    print("Testing SMTP connections...")
    working_smtps = []
    for smtp in smtps:
        if test_smtp_connection(smtp):
            working_smtps.append(smtp)
            print(f"  ✓ {smtp['host']}:{smtp['port']}")
        else:
            print(f"  ✗ {smtp['host']}:{smtp['port']} - failed")
    
    if not working_smtps:
        logger.error("No working SMTP servers found")
        sys.exit(1)
    
    smtps = working_smtps
    logger.info(f"Using {len(smtps)} working SMTP servers")
    
    # Load recipients and template
    recipients = load_recipients()
    template = load_template()
    
    if args.test:
        recipients = recipients[:5]
        print(f"\n🧪 TEST MODE: Sending to first {len(recipients)} recipients")
    
    if config.get('dry_run'):
        print(f"\n🧪 DRY RUN MODE: No emails will be sent")
        print(f"   Would send {len(recipients)} emails using {len(smtps)} SMTP servers")
        print(f"   Subject: {config['subject']}")
        print(f"   From: {config['sender_name']} <{config['sender_email']}>")
        print(f"   Delay: {config.get('delay_between_emails', 2)}s between emails")
        print(f"   Retries: {config.get('max_retries', 3)} per email")
        print(f"   Threads: {config.get('thread_count', 5)}")
        print("\n✅ Dry run complete. Remove --dry-run to send real emails.")
        return
    
    # Send emails
    print(f"\n📧 Sending {len(recipients)} emails...")
    print(f"   Using {len(smtps)} SMTP servers (round-robin)")
    print(f"   Delay: {config.get('delay_between_emails', 2)}s between sends")
    print("-" * 40 + "\n")
    
    # Use threading for concurrent sends
    max_threads = config.get('thread_count', 5)
    success_count = 0
    fail_count = 0
    results_lock = threading.Lock()
    
    def worker(recipient):
        nonlocal success_count, fail_count
        result = process_recipient(
            recipient, smtps, config, template,
            config.get('max_retries', 3)
        )
        
        with results_lock:
            if result:
                success_count += 1
            else:
                fail_count += 1
        
        # Respect delay
        time.sleep(config.get('delay_between_emails', 2))
    
    # Process with thread pool
    threads = []
    for recipient in recipients:
        if len(threads) >= max_threads:
            for t in threads:
                t.join()
            threads = []
        
        t = threading.Thread(target=worker, args=(recipient,))
        t.start()
        threads.append(t)
    
    # Wait for remaining threads
    for t in threads:
        t.join()
    
    # Final summary
    print("\n" + "=" * 50)
    print("📊 FINAL SUMMARY")
    print("=" * 50)
    print(f"Total recipients: {len(recipients)}")
    print(f"✓ Sent: {success_count}")
    print(f"✗ Failed: {fail_count}")
    print(f"📁 Logs: send_log.csv, error_log.txt, email_system.log")
    print("\n✅ Done.\n")

if __name__ == "__main__":
    main()
