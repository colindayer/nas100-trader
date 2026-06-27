"""
alerts.py — Send fill/error/daily-summary notifications.

Priority order:
  1. Telegram  — if config.ini [alerts] has telegram_token + chat_id
  2. Email     — if config.ini [alerts] has smtp_host + smtp_user + smtp_pass + to_email
  3. Console   — always (fallback; never silently drops)
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText

import requests

from broker import load_config

logger = logging.getLogger("trader")
_cfg   = load_config("alerts")


def send(msg: str) -> None:
    """Dispatch an alert through available channels; always prints to console."""
    print(f"[ALERT] {msg}")
    logger.info(f"ALERT {msg}")
    _try_telegram(msg)
    _try_email(msg)


def _try_telegram(msg: str) -> None:
    token   = _cfg.get("telegram_token", "")
    chat_id = _cfg.get("chat_id", "")
    if not token or not chat_id or token.startswith("YOUR_"):
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg},
            timeout=10,
        )
        if not resp.ok:
            logger.warning(f"Telegram alert failed: {resp.text}")
    except Exception as e:
        logger.warning(f"Telegram alert error: {e}")


def _try_email(msg: str) -> None:
    host     = _cfg.get("smtp_host", "")
    user     = _cfg.get("smtp_user", "")
    password = _cfg.get("smtp_pass", "")
    to_addr  = _cfg.get("to_email", "")
    if not all([host, user, password, to_addr]) or host.startswith("YOUR_"):
        return
    try:
        port = int(_cfg.get("smtp_port", 587))
        mime = MIMEText(msg)
        mime["Subject"] = f"[Trader] {msg[:60]}"
        mime["From"]    = user
        mime["To"]      = to_addr
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.ehlo(); s.starttls(); s.login(user, password)
            s.send_message(mime)
    except Exception as e:
        logger.warning(f"Email alert error: {e}")
