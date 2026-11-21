"""OTP email delivery via stdlib smtplib (PLAN.md §7/§11)."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from . import config

log = logging.getLogger("swarraksha.mailer")


def send_otp_email(to_email: str, code: str) -> bool:
    """Send the OTP by email. Returns True on success, False if SMTP is
    not configured. Raises on delivery failure so callers fail closed."""
    if not config.smtp_configured():
        return False
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = "Your SwarRaksha sign-in code"
    msg.set_content(
        f"Your SwarRaksha sign-in code is {code}.\n"
        f"It is valid for {config.OTP_TTL_MIN} minutes. "
        "If you did not request this code, you can ignore this email.\n")
    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
    try:
        if config.SMTP_PORT != 465 and config.SMTP_USE_TLS:
            server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return True
