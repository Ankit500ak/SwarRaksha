"""API configuration (environment-driven).

DEV_MODE: when true, login OTPs are printed to the server log so the
flow can be exercised locally without an email provider. OTPs are NEVER
returned in API responses, in any mode. Production must run with
DEV_MODE=false and a real mail/SMS sender wired into auth.request_otp.
"""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'swarraksha.db')}")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-secret-change-in-production")
JWT_ALG = "HS256"
JWT_TTL_DAYS = 7
DEV_MODE = os.environ.get("SWAR_DEV_MODE", "1") == "1"
OTP_TTL_MIN = 10
OTP_LENGTH = 6
# Voiceprint cosine threshold for the MFCC baseline. Starting value only —
# NOT calibrated (see services/ml-inference/MODEL_CARD.md).
VOICEPRINT_THRESHOLD = float(os.environ.get("VOICEPRINT_THRESHOLD", "0.80"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_CLIP_SECONDS = 120
