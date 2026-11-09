# Gmail → Telegram: free email alert bridge

This script checks Gmail over IMAP/TLS for unread Avito alert emails and forwards emails containing an Avito listing URL to Telegram. It does not scrape Avito and only forwards alerts Avito sends to Gmail; coverage and delivery timing depend on Avito's notification settings.

## Security first
If a Telegram bot token was committed to this public repository, revoke that exposed token in @BotFather (`/revoke`) and use a new token. Never commit `.env`, bot tokens, Gmail app passwords, or other secrets.

## Gmail
1. Enable 2-Step Verification on the Google Account.
2. Create an App Password in Google Account → Security → 2-Step Verification → App passwords, if available for the account.
3. Use the 16-character app password, not the normal Gmail password.
4. Enable email notifications for saved searches on Avito.

## Run on Mac
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install python-dotenv
```
Copy `.env.gmail.example` to `.env` locally, fill it in, then run:
```bash
python gmail_avito_watcher.py
```
Find your Telegram chat ID by sending `/start` to your bot and using a trusted bot update viewer; never share the token. Keep the Mac awake and online while the script runs. This first version forwards links only; AI valuation and 24/7 cloud monitoring are not included.
