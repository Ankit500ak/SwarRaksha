"""Email-OTP auth + JWT sessions.

DEV_MODE: OTPs are printed to the server log ONLY (never returned in a
response) so the local flow can be tested without a mail provider.
Production: set SWAR_DEV_MODE=0 and wire a real sender in request_otp.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import secrets

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .config import DEV_MODE, JWT_ALG, JWT_SECRET, JWT_TTL_DAYS, OTP_LENGTH, OTP_TTL_MIN
from .db import get_db

log = logging.getLogger("swarraksha.auth")
bearer = HTTPBearer(auto_error=False)


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def request_otp(db: Session, email: str) -> None:
    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=OTP_TTL_MIN)
    db.add(models.OtpCode(email=email.lower(), code_hash=_hash(code), expires_at=expires))
    db.commit()
    if DEV_MODE:
        # Log-only delivery for local development. Never in responses.
        log.warning("[DEV_MODE] OTP for %s is %s (valid %d min)", email, code, OTP_TTL_MIN)
    else:
        # TODO(production): send via the configured email provider here.
        log.info("OTP requested for %s (delivery provider not configured)", email)


def verify_otp(db: Session, email: str, code: str) -> models.User:
    now = dt.datetime.now(dt.timezone.utc)
    row = (db.query(models.OtpCode)
           .filter(models.OtpCode.email == email.lower(),
                   models.OtpCode.used.is_(False))
           .order_by(models.OtpCode.id.desc()).first())
    if row is None or row.code_hash != _hash(code):
        raise HTTPException(401, "Invalid code")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires < now:
        raise HTTPException(401, "Code expired")
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
