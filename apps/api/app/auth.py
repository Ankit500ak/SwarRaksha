"""Email-OTP auth + JWT sessions.

OTP storage: only a salted HMAC-SHA256 hash is stored
(``v2:<salt>:<hmac>``, keyed with the server secret). Codes expire after
OTP_TTL_MIN minutes, allow at most OTP_MAX_ATTEMPTS verify attempts, and
requests are limited per email and per IP over a rolling window.
Legacy rows holding a bare sha256(code) digest (written before salted
hashing, and by the test fixtures) are still accepted on verify.

Delivery: SMTP via app/mailer.py when configured; in DEV_MODE the code
is also printed to the server log (local only). Codes are NEVER returned
in API responses in any mode.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import secrets

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import mailer, models
from .config import (DEV_MODE, JWT_ALG, JWT_SECRET, JWT_TTL_DAYS,
                     OTP_LENGTH, OTP_MAX_ATTEMPTS,
                     OTP_MAX_REQUESTS_PER_EMAIL, OTP_MAX_REQUESTS_PER_IP,
                     OTP_REQUEST_WINDOW_MIN, OTP_TTL_MIN)
from .db import get_db

log = logging.getLogger("swarraksha.auth")
bearer = HTTPBearer(auto_error=False)


def _hash(code: str) -> str:
    """Legacy unsalted hash — kept only to verify pre-existing rows."""
    return hashlib.sha256(code.encode()).hexdigest()


def _hash_salted(code: str) -> str:
    salt = secrets.token_hex(16)
    digest = hmac.new(JWT_SECRET.encode(), f"{salt}:{code}".encode(),
                      hashlib.sha256).hexdigest()
    return f"v2:{salt}:{digest}"


def _verify_hash(stored: str, code: str) -> bool:
    if stored.startswith("v2:"):
        try:
            _, salt, digest = stored.split(":", 2)
        except ValueError:
            return False
        expected = hmac.new(JWT_SECRET.encode(), f"{salt}:{code}".encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
    return hmac.compare_digest(_hash(code), stored)


def _recent_requests(db: Session, *, email: str | None = None,
                     ip: str | None = None) -> int:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=OTP_REQUEST_WINDOW_MIN)
    # created_at may be tz-naive (SQLite) or aware depending on backend;
    # compare in Python to avoid tz pitfalls across backends.
    rows = db.query(models.OtpCode).all()
    count = 0
    for r in rows:
        created = r.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.timezone.utc)
        if created < since:
            continue
        if email is not None and r.email != email.lower():
            continue
        if ip is not None and r.request_ip != ip:
            continue
        count += 1
    return count


def request_otp(db: Session, email: str, ip: str | None = None) -> None:
    if _recent_requests(db, email=email) >= OTP_MAX_REQUESTS_PER_EMAIL:
        raise HTTPException(429, "Too many code requests; try again later")
    if ip and _recent_requests(db, ip=ip) >= OTP_MAX_REQUESTS_PER_IP:
        raise HTTPException(429, "Too many code requests; try again later")
    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=OTP_TTL_MIN)
    db.add(models.OtpCode(email=email.lower(), code_hash=_hash_salted(code),
                          expires_at=expires, attempts=0, request_ip=ip))
    db.commit()
    delivered = False
    try:
        delivered = mailer.send_otp_email(email.lower(), code)
    except Exception:
        log.exception("OTP email delivery failed for %s", email)
        if not DEV_MODE:
            raise HTTPException(503, "Could not send the sign-in code; try again later")
    if DEV_MODE:
        # Log-only delivery for local development. Never in responses.
        log.warning("[DEV_MODE] OTP for %s is %s (valid %d min)", email, code, OTP_TTL_MIN)
    elif not delivered:
        log.error("OTP requested for %s but SMTP is not configured", email)
        raise HTTPException(503, "Email delivery is not configured")


def verify_otp(db: Session, email: str, code: str) -> models.User:
    now = dt.datetime.now(dt.timezone.utc)
    row = (db.query(models.OtpCode)
           .filter(models.OtpCode.email == email.lower(),
                   models.OtpCode.used.is_(False))
           .order_by(models.OtpCode.id.desc()).first())
    if row is None:
        raise HTTPException(401, "Invalid code")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires < now:
        raise HTTPException(401, "Code expired")
    if (row.attempts or 0) >= OTP_MAX_ATTEMPTS:
        row.used = True
        db.commit()
        raise HTTPException(429, "Too many attempts; request a new code")
    if not _verify_hash(row.code_hash, code):
        row.attempts = (row.attempts or 0) + 1
        if row.attempts >= OTP_MAX_ATTEMPTS:
            row.used = True
        db.commit()
        raise HTTPException(401, "Invalid code")
    row.used = True
    user = db.query(models.User).filter(models.User.email == email.lower()).first()
    if user is None:
        user = models.User(email=email.lower())
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_token(user: models.User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=JWT_TTL_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer),
                     db: Session = Depends(get_db)) -> models.User:
    if creds is None:
        raise HTTPException(401, "Not signed in")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid session")
    user = db.get(models.User, int(payload["sub"]))
    if user is None:
        raise HTTPException(401, "Unknown user")
    return user
