#!/usr/bin/env python3
"""
Email Automation System
Author: [Your Name]
Description: High-performance SMTP email sender with threading, template variables,
             and SMTP rotation. Built for legitimate business email workflows.
"""

import base64
import datetime
import json
import logging
import math
import os
import random
import smtplib
import string
import sys
import time
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.utils import formataddr, make_msgid
from threading import Lock, Thread
from typing import Dict, List, Optional

# Optional imports with fallbacks
try:
    from faker import Faker
    FAKER_AVAILABLE = True
except ImportError:
    FAKER_AVAILABLE = False
    print("Warning: Faker not installed. Template variables will be limited.")

try:
    import tldextract
    TLDEXTRACT_AVAILABLE = True
except ImportError:
    TLDEXTRACT_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('logs/email_automator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Separate error log
error_logger = logging.getLogger('errors')
error_handler = logging.FileHandler('logs/errors.log')
error_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
error_logger.addHandler(error_handler)


class EmailAutomationSystem:
    """Professional email automation system with SMTP rotation and templating."""
    
    def __init__(self, config_path: str = 'config.json'):
        self.config_path = config_path
        self.config = None
        self.smtp_servers: Dict = {}
        self.target_emails: List[str] = []
        self.attachment_path: Optional[str] = None
        self.letter_path: Optional[str] = None
        self.lock = Lock()
        self.email_counter = 0
        
        self._load_config()
        self._setup_directories()
        self._load_files()
        
    def _load_config(self):
        """Load configuration from JSON file."""
        if not os.path.exists(self.config_path):
            self._create_default_config()
            
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)
        logger.info("Configuration loaded")
    
    def _create_default_config(self):
        """Create default configuration template."""
        default_config = {
            "smtp_settings": {
                "thread_count_check": 50,
                "thread_count_send": 30,
                "delay_between_emails": 1,
                "auto_remove_dead_smtps": False
            },
            "email_settings": {
                "subject": "Your personalized message",
                "sender_name": "Your Name",
                "sender_email": "your@email.com",
                "force_smtp_match": False,
                "force_spoof": False
            },
            "template_variables": {
                "enabled": True,
                "note": "Use ##variable## in templates. See README for options."
            },
            "headers": {}
        }
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default config at {self.config_path}")
        print("Please edit config.json before running again.")
        sys.exit(0)
    
    def _setup_directories(self):
        """Ensure required directories exist."""
        dirs = ['FILES/EMAILS', 'FILES/LETTER', 'FILES/SMTPS', 'FILES/ATTACHMENT', 'logs']
        for d in dirs:
            os.makedirs(d, exist_ok=True)
    
    def _load_files(self):
        """Load emails, template, SMTP credentials, and attachment."""
        # Load emails
        email_files = [f for f in os.listdir('FILES/EMAILS') if f.endswith(('.csv', '.txt'))]
        if not email_files:
            logger.error("No email list found in FILES/EMAILS/")
            sys.exit(1)
        
        email_path = os.path.join('FILES/EMAILS', email_files[0])
        with open(email_path, 'r') as f:
            self.target_emails = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(self.target_emails)} target emails")
        
        # Load letter template
        letter_files = [f for f in os.listdir('FILES/LETTER') if f.endswith(('.html', '.txt'))]
        if not letter_files:
            logger.error("No letter template found in FILES/LETTER/")
            sys.exit(1)
        self.letter_path = os.path.join('FILES/LETTER', letter_files[0])
        
        # Load SMTP credentials
        smtp_files = [f for f in os.listdir('FILES/SMTPS') if f.endswith(('.csv', '.txt'))]
        if not smtp_files:
            logger.error("No SMTP credentials found in FILES/SMTPS/")
            sys.exit(1)
        self._load_smtp_credentials(os.path.join('FILES/SMTPS', smtp_files[0]))
        
        # Load attachment (optional)
        attachment_files = os.listdir('FILES/ATTACHMENT')
        if attachment_files:
            self.attachment_path = os.path.join('FILES/ATTACHMENT', attachment_files[0])
    
    def _load_smtp_credentials(self, path: str):
        """Load and validate SMTP credentials."""
        with open(path, 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
        
        for line in lines:
            parts = line.split('|')
            if len(parts) == 4:
                host, port, user, password = parts
                self.smtp_servers[user] = {
                    'host': host,
                    'port': port,
                    'user': user,
                    'password': password,
                    'server': None
                }
        logger.info(f"Loaded {len(self.smtp_servers)} SMTP servers")
    
    def verify_smtp_servers(self):
        """Test all SMTP connections before sending."""
        logger.info("Verifying SMTP servers...")
        live_servers = {}
        
        for user, creds in self.smtp_servers.items():
            try:
                server = self._connect_smtp(creds)
                if server:
                    creds['server'] = server
                    live_servers[user] = creds
                    logger.info(f"✓ SMTP live: {creds['host']}:{creds['port']}")
                else:
                    logger.warning(f"✗ SMTP failed: {creds['host']}:{creds['port']}")
            except Exception as e:
                error_logger.error(f"SMTP verification failed for {creds['host']}: {e}")
        
        self.smtp_servers = live_servers
        
        if not self.smtp_servers:
            logger.error("No live SMTP servers available")
            sys.exit(1)
        
        logger.info(f"{len(self.smtp_servers)} live SMTP servers ready")
    
    def _connect_smtp(self, creds: Dict):
        """Establish SMTP connection."""
        host, port, user, password = creds['host'], creds['port'], creds['user'], creds['password']
        
        if port == '465':
            server = smtplib.SMTP_SSL(host, int(port), timeout=15)
        else:
            server = smtplib.SMTP(host, int(port), timeout=15)
            server.starttls()
        
        server.ehlo()
        server.login(user, password)
        return server
    
    def _replace_variables(self, text: str, email: str, smtp_user: str = '') -> str:
        """Replace template variables with dynamic content."""
        if not FAKER_AVAILABLE:
            # Basic replacements only
            text = text.replace('##email##', email)
            text = text.replace('##username##', email.split('@')[0])
            return text
        
        fake = Faker()
        
        # Email-based replacements
        if '##email##' in text:
            text = text.replace('##email##', email)
        if '##username##' in text:
            text = text.replace('##username##', email.split('@')[0])
        if '##domain##' in text and TLDEXTRACT_AVAILABLE:
            domain = tldextract.extract(email.split('@')[1]).domain
            text = text.replace('##domain##', domain)
        
        # Date replacements
        now = datetime.datetime.now()
        text = text.replace('##current_date##', now.strftime('%Y-%m-%d'))
        text = text.replace('##current_time##', now.strftime('%H:%M'))
        text = text.replace('##current_year##', now.strftime('%Y'))
        
        # Faker replacements (limited set for professionalism)
        if '##random_name##' in text:
            text = text.replace('##random_name##', fake.name())
        if '##random_city##' in text:
            text = text.replace('##random_city##', fake.city())
        
        return text
    
    def _build_message(self, email: str, smtp_creds: Dict):
        """Build email message with template and optional attachment."""
        msg = EmailMessage()
        
        # Sender and recipient
        sender_name = self._replace_variables(
            self.config['email_settings']['sender_name'], email, smtp_creds['user']
        )
        sender_email = self.config['email_settings']['sender_email']
        
        msg['From'] = formataddr((sender_name, sender_email))
        msg['To'] = email
        msg['Subject'] = self._replace_variables(
            self.config['email_settings']['subject'], email, smtp_creds['user']
        )
        
        # Add custom headers
        for key, value in self.config.get('headers', {}).items():
            msg[key] = self._replace_variables(value, email, smtp_creds['user'])
        
        # Load and process HTML template
        with open(self.letter_path, 'r') as f:
            html_content = f.read()
        html_content = self._replace_variables(html_content, email, smtp_creds['user'])
        msg.add_alternative(html_content, subtype='html')
        
        # Add attachment if exists
        if self.attachment_path and os.path.exists(self.attachment_path):
            with open(self.attachment_path, 'rb') as f:
                attachment_data = f.read()
            attachment = MIMEApplication(attachment_data)
            attachment.add_header(
                'Content-Disposition', 
                'attachment', 
                filename=os.path.basename(self.attachment_path)
            )
            msg.attach(attachment)
        
        return msg
    
    def _send_single_email(self, email: str):
        """Send one email using round-robin SMTP selection."""
        smtp_keys = list(self.smtp_servers.keys())
        smtp_user = smtp_keys[self.email_counter % len(smtp_keys)]
        smtp_creds = self.smtp_servers[smtp_user]
        
        try:
            msg = self._build_message(email, smtp_creds)
            
            # Reconnect if needed
            if smtp_creds['server'] is None:
                smtp_creds['server'] = self._connect_smtp(smtp_creds)
            
            smtp_creds['server'].send_message(msg)
            logger.info(f"✓ Sent to {email} via {smtp_creds['host']}")
            
        except Exception as e:
            error_logger.error(f"Failed to send to {email}: {e}")
            logger.warning(f"✗ Failed to send to {email}")
            
            # Try to reconnect on failure
            try:
                smtp_creds['server'] = self._connect_smtp(smtp_creds)
                smtp_creds['server'].send_message(msg)
                logger.info(f"✓ Retry successful for {email}")
            except Exception as retry_error:
                error_logger.error(f"Retry failed for {email}: {retry_error}")
        
        with self.lock:
            self.email_counter += 1
        
        # Delay between emails
        time.sleep(self.config['smtp_settings'].get('delay_between_emails', 1))
    
    def run(self):
        """Main execution method."""
        print("\n" + "="*60)
        print("EMAIL AUTOMATION SYSTEM")
        print("="*60)
        print(f"Targets: {len(self.target_emails)} emails")
        print(f"SMTP Servers: {len(self.smtp_servers)}")
        print(f"Template: {os.path.basename(self.letter_path)}")
        print("="*60 + "\n")
        
        self.verify_smtp_servers()
        
        thread_count = self.config['smtp_settings'].get('thread_count_send', 30)
        thread_count = min(thread_count, len(self.target_emails))
        
        logger.info(f"Starting send with {thread_count} threads...")
        
        threads = []
        email_queue = self.target_emails.copy()
        
        def worker():
            while True:
                try:
                    email = email_queue.pop()
                except IndexError:
                    break
                self._send_single_email(email)
        
        for _ in range(thread_count):
            t = Thread(target=worker)
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
        
        logger.info(f"Completed. Sent to {self.email_counter} of {len(self.target_emails)} emails")


def main():
    """Entry point."""
    automator = EmailAutomationSystem()
    automator.run()


if __name__ == '__main__':
    main()