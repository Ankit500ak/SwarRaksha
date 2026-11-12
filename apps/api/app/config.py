"""API configuration (environment-driven), fail-closed in production.

SWAR_ENV selects the posture:
  * ``dev`` (default) — local-friendly: OTPs may be printed to the server
    log when SWAR_DEV_MODE=1, SQLite is fine, voiceprint key may be
    derived from JWT_SECRET as a documented dev fallback.
  * ``production`` — ``validate_config()`` must return no errors or the
    app refuses to boot (see main.py). JWT secret must be long and
    non-default, SWAR_DEV_MODE must be off, a valid 32-byte
    VOICEPRINT_ENC_KEY is required, SQLite needs an explicit opt-in
    (SWAR_ALLOW_SQLITE=1), SMTP must be configured, and CORS must not
    contain a wildcard.
"""
from __future__ import annotations

import base64
import binascii
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_JWT_SECRET = "dev-only-secret-change-in-production"

DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'swarraksha.db')}")
JWT_SECRET = os.environ.get("JWT_SECRET", DEFAULT_JWT_SECRET)
JWT_ALG = "HS256"
JWT_TTL_DAYS = 7
DEV_MODE = os.environ.get("SWAR_DEV_MODE", "1") == "1"
SWAR_ENV = os.environ.get("SWAR_ENV", "dev").strip().lower()
ALLOW_SQLITE = os.environ.get("SWAR_ALLOW_SQLITE", "0") == "1"

OTP_TTL_MIN = 10
OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
OTP_MAX_REQUESTS_PER_EMAIL = int(os.environ.get("OTP_MAX_REQUESTS_PER_EMAIL", "3"))
OTP_MAX_REQUESTS_PER_IP = int(os.environ.get("OTP_MAX_REQUESTS_PER_IP", "10"))
OTP_REQUEST_WINDOW_MIN = int(os.environ.get("OTP_REQUEST_WINDOW_MIN", "15"))

# --- SMTP (OTP delivery in production) -----------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"  # STARTTLS

# --- Voiceprint encryption ------------------------------------------------
VOICEPRINT_ENC_KEY = os.environ.get("VOICEPRINT_ENC_KEY", "")

# Voiceprint cosine threshold. Defaults are backend-specific starting
# points from the 2026-11-12 eval (docs/evals/2026-11-12-pretrained-models.md):
# MFCC cosines cluster near 1.0 for everyone (0.80 is a plumbing value, not
# a calibrated operating point); ECAPA measured same-speaker mean 0.78 vs
# different-speaker mean 0.24 on LibriSpeech, so 0.55 sits between the two
# distributions. An explicit VOICEPRINT_THRESHOLD always wins.
_VP_BACKEND = os.environ.get("SWAR_VOICEPRINT_BACKEND", "mfcc").lower()
_VP_DEFAULT_THRESHOLD = "0.55" if _VP_BACKEND == "ecapa" else "0.80"
VOICEPRINT_THRESHOLD = float(os.environ.get(
    "VOICEPRINT_THRESHOLD", _VP_DEFAULT_THRESHOLD))

# --- Uploads ---------------------------------------------------------------
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_CLIP_SECONDS = float(os.environ.get("MAX_CLIP_SECONDS", "120"))
# Whole-request ceiling (multipart overhead + up to 3 enrollment samples).
MAX_REQUEST_BYTES = int(os.environ.get(
    "MAX_REQUEST_BYTES", str(3 * MAX_UPLOAD_BYTES + 1024 * 1024)))

# --- CORS ------------------------------------------------------------------
def _parse_origins(raw: str | None) -> list[str]:
    if raw is None or raw.strip() == "":
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]

CORS_ORIGINS = _parse_origins(os.environ.get("CORS_ORIGINS"))

# --- Rate limiting (in-memory, per IP) -------------------------------------
RATE_LIMIT_GLOBAL_PER_MIN = int(os.environ.get("RATE_LIMIT_GLOBAL_PER_MIN", "300"))
RATE_LIMIT_AUTH_PER_MIN = int(os.environ.get("RATE_LIMIT_AUTH_PER_MIN", "20"))
RATE_LIMIT_CLIP_PER_MIN = int(os.environ.get("RATE_LIMIT_CLIP_PER_MIN", "30"))


def smtp_configured(env: dict | None = None) -> bool:
    e = env if env is not None else os.environ
    return bool(e.get("SMTP_HOST") if env is not None else SMTP_HOST) and \
        bool(e.get("SMTP_FROM") if env is not None else SMTP_FROM)


def decode_enc_key(raw: str) -> bytes | None:
    """Return the 32-byte key for a base64 string, or None if invalid."""
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None
    return key if len(key) == 32 else None


def validate_config(env: dict | None = None) -> list[str]:
    """Return production-config errors (empty list = safe to boot).

    Pure function of the supplied env mapping (defaults to os.environ plus
    this module's already-parsed values) so tests can exercise every
    fail-closed branch without reloading modules. Only meaningful when
    SWAR_ENV=production; in dev it always returns [].
    """
    e = dict(os.environ) if env is None else dict(env)
    swar_env = e.get("SWAR_ENV", SWAR_ENV).strip().lower()
    if swar_env != "production":
        return []
    errors: list[str] = []
    secret = e.get("JWT_SECRET", JWT_SECRET)
    if not secret or secret == DEFAULT_JWT_SECRET or len(secret) < 32:
        errors.append("JWT_SECRET must be set, non-default and >= 32 chars in production")
    if e.get("SWAR_DEV_MODE", "1" if DEV_MODE else "0") == "1":
        errors.append("SWAR_DEV_MODE must be 0 in production")
    key_raw = e.get("VOICEPRINT_ENC_KEY", VOICEPRINT_ENC_KEY)
    if not key_raw or decode_enc_key(key_raw) is None:
        errors.append("VOICEPRINT_ENC_KEY must be a base64-encoded 32-byte key in production")
    db_url = e.get("DATABASE_URL", DATABASE_URL)
    allow_sqlite = e.get("SWAR_ALLOW_SQLITE", "1" if ALLOW_SQLITE else "0") == "1"
    if db_url.startswith("sqlite") and not allow_sqlite:
        errors.append("DATABASE_URL must not be SQLite in production (set SWAR_ALLOW_SQLITE=1 to override explicitly)")
    if not (e.get("SMTP_HOST", SMTP_HOST) and e.get("SMTP_FROM", SMTP_FROM)):
        errors.append("SMTP must be configured in production (SMTP_HOST and SMTP_FROM)")
    origins = _parse_origins(e.get("CORS_ORIGINS", ",".join(CORS_ORIGINS)))
    if "*" in origins:
        errors.append("CORS_ORIGINS must not contain '*' in production")
    return errors
