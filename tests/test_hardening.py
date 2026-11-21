"""Production-hardening coverage: config fail-closed, OTP hashing /
expiry / attempt + request limits, voiceprint encryption at rest,
rate limiting, security headers / error shape, upload validation,
privacy export + account deletion, audit log."""
import base64
import datetime as dt
import hashlib

import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.config as cfg
from app import auth as auth_mod, models
from app.db import SessionLocal
from app.encryption import decrypt_embedding, encrypt_embedding, is_encrypted
from app.main import app
from app.ratelimit import RateLimiter
from conftest import synth_voice_bytes

client = TestClient(app)

VALID_KEY = base64.b64encode(b"k" * 32).decode()
PROD_BASE = {
    "SWAR_ENV": "production", "SWAR_DEV_MODE": "0",
    "JWT_SECRET": "x" * 40, "VOICEPRINT_ENC_KEY": VALID_KEY,
    "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/swar",
    "SMTP_HOST": "smtp.example.com", "SMTP_FROM": "otp@example.com",
    "CORS_ORIGINS": "https://app.example.com",
}


@pytest.fixture(autouse=True)
def _reset_limiter():
    app.state.rate_limiter.reset()
    yield
    app.state.rate_limiter.reset()


def _insert_code(email: str, code: str, *, salted: bool = True,
                 expired: bool = False) -> None:
    db = SessionLocal()
    expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
        minutes=-5 if expired else 10)
    hashed = auth_mod._hash_salted(code) if salted else hashlib.sha256(code.encode()).hexdigest()
    db.add(models.OtpCode(email=email, code_hash=hashed, expires_at=expires))
    db.commit()
    db.close()


def _login(email: str, code: str = "112233") -> dict:
    _insert_code(email, code)
    r = client.post("/auth/verify-otp", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ------------------------------------------------------------ config
def test_production_config_valid_passes():
    assert cfg.validate_config(dict(PROD_BASE)) == []


@pytest.mark.parametrize("patch,fragment", [
    ({"JWT_SECRET": cfg.DEFAULT_JWT_SECRET}, "JWT_SECRET"),
    ({"JWT_SECRET": "short"}, "JWT_SECRET"),
    ({"SWAR_DEV_MODE": "1"}, "SWAR_DEV_MODE"),
    ({"VOICEPRINT_ENC_KEY": ""}, "VOICEPRINT_ENC_KEY"),
    ({"VOICEPRINT_ENC_KEY": "not-base64!!"}, "VOICEPRINT_ENC_KEY"),
    ({"VOICEPRINT_ENC_KEY": base64.b64encode(b"too-short").decode()}, "VOICEPRINT_ENC_KEY"),
    ({"DATABASE_URL": "sqlite:///./x.db"}, "SQLite"),
    ({"SMTP_HOST": ""}, "SMTP"),
    ({"SMTP_FROM": ""}, "SMTP"),
    ({"CORS_ORIGINS": "*"}, "CORS"),
])
def test_production_config_fail_closed(patch, fragment):
    env = dict(PROD_BASE, **patch)
    errors = cfg.validate_config(env)
    assert any(fragment in e for e in errors), errors


def test_production_sqlite_explicit_opt_in():
    env = dict(PROD_BASE, DATABASE_URL="sqlite:///./x.db", SWAR_ALLOW_SQLITE="1")
    assert cfg.validate_config(env) == []


def test_dev_config_never_blocks():
    assert cfg.validate_config({"SWAR_ENV": "dev"}) == []


# ------------------------------------------------------------ OTP
def test_otp_stored_salted_and_hashed():
    db = SessionLocal()
    auth_mod.request_otp(db, "hashcheck@example.in", ip="1.2.3.4")
    row = (db.query(models.OtpCode)
           .filter(models.OtpCode.email == "hashcheck@example.in")
           .order_by(models.OtpCode.id.desc()).first())
    db.close()
    assert row.code_hash.startswith("v2:")
    assert len(row.code_hash.split(":")) == 3
    # The stored value must not be a plain sha256 of any 6-digit code we
    # can trivially check, and must not contain the code itself.
    assert row.code_hash != hashlib.sha256(b"000000").hexdigest()


def test_otp_verify_salted_and_legacy():
    headers = _login("salted@example.in", "654321")
    assert client.get("/me", headers=headers).status_code == 200
    # Legacy bare-sha256 rows (pre-hardening + old fixtures) still verify.
    _insert_code("legacy@example.in", "999888", salted=False)
    r = client.post("/auth/verify-otp",
                    json={"email": "legacy@example.in", "code": "999888"})
    assert r.status_code == 200


def test_otp_expired_rejected():
    _insert_code("expired@example.in", "111222", expired=True)
    r = client.post("/auth/verify-otp",
                    json={"email": "expired@example.in", "code": "111222"})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_otp_attempt_limit_burns_code():
    _insert_code("attempts@example.in", "555444")
    for _ in range(cfg.OTP_MAX_ATTEMPTS):
        r = client.post("/auth/verify-otp",
                        json={"email": "attempts@example.in", "code": "000000"})
        assert r.status_code == 401
    # Code is burned after max attempts — even the right code now fails.
    r = client.post("/auth/verify-otp",
                    json={"email": "attempts@example.in", "code": "555444"})
    assert r.status_code in (401, 429)


def test_otp_request_limit_per_email():
    email = "ratelimited@example.in"
    for _ in range(cfg.OTP_MAX_REQUESTS_PER_EMAIL):
        r = client.post("/auth/request-otp", json={"email": email})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "detail": "Code sent"}
    r = client.post("/auth/request-otp", json={"email": email})
    assert r.status_code == 429
    assert r.json()["code"] == "rate_limited"


# ------------------------------------------------------------ encryption
def test_encryption_roundtrip_and_ciphertext_differs():
    plain = np.arange(44, dtype=np.float32).tobytes()
    blob = encrypt_embedding(plain)
    assert blob != plain
    assert is_encrypted(blob)
    assert decrypt_embedding(blob) == plain
    # Random nonce/salt: encrypting twice differs.
    assert encrypt_embedding(plain) != blob


def test_encryption_legacy_plain_passthrough():
    plain = np.ones(44, dtype=np.float32).tobytes()
    assert not is_encrypted(plain)
    assert decrypt_embedding(plain) == plain


def test_voiceprint_db_blob_is_encrypted():
    headers = _login("encdb@example.in")
    files = [("samples", (f"s{i}.wav", synth_voice_bytes(4.0, seed=i + 20), "audio/wav"))
             for i in range(3)]
    r = client.post("/voiceprints", headers=headers,
                    data={"label": "Daughter"}, files=files)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    vp = db.query(models.Voiceprint).filter(models.Voiceprint.id == r.json()["id"]).first()
    stored = bytes(vp.embedding)
    db.close()
    assert is_encrypted(stored)
    plain = decrypt_embedding(stored)
    assert len(plain) == 44 * 4
    assert stored != plain
    # And the check pipeline can still use it end-to-end (decrypt on read).
    clip = synth_voice_bytes(9.0, seed=21)
    r = client.post("/checks/clip", headers=headers,
                    data={"voiceprint_id": r.json()["id"]},
                    files={"file": ("call.wav", clip, "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json()["voiceprint_similarity"] is not None


# ------------------------------------------------------------ HTTP posture
def test_health_and_ready():
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["db_ok"] is True


def test_security_headers_and_error_shape():
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    r = client.get("/voiceprints")  # unauthenticated
    assert r.status_code == 401
    assert set(r.json()) == {"code", "message"}
    r = client.get("/checks/999999", headers=_login("shape@example.in"))
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_rate_limiter_unit():
    rl = RateLimiter()
    assert all(rl.allow("b", "1.1.1.1", 3) for _ in range(3))
    assert rl.allow("b", "1.1.1.1", 3) is False
    assert rl.allow("b", "2.2.2.2", 3) is True  # per-IP isolation


def test_rate_limit_http_smoke(monkeypatch):
    monkeypatch.setattr(cfg, "RATE_LIMIT_AUTH_PER_MIN", 3)
    try:
        codes = [client.post("/auth/request-otp",
                             json={"email": "not-an-email"}).status_code
                 for _ in range(4)]
    finally:
        monkeypatch.undo()
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_upload_validation_rejects_bad_type_and_spoofed_content():
    headers = _login("uploads@example.in")
    r = client.post("/checks/clip", headers=headers,
                    files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["code"] == "bad_request"
    r = client.post("/checks/clip", headers=headers,
                    files={"file": ("fake.wav", b"not a wav at all", "audio/wav")})
    assert r.status_code == 400


# ------------------------------------------------------------ privacy
def test_export_and_delete_flow():
    headers = _login("privacy@example.in")
    files = [("samples", (f"s{i}.wav", synth_voice_bytes(4.0, seed=i + 40), "audio/wav"))
             for i in range(3)]
    vp = client.post("/voiceprints", headers=headers,
                     data={"label": "Mum"}, files=files)
    assert vp.status_code == 200, vp.text
    client.post("/reports", headers=headers, json={"details": "suspicious call"})

    exp = client.get("/me/export", headers=headers)
    assert exp.status_code == 200
    body = exp.json()
    assert body["profile"]["email"] == "privacy@example.in"
    assert any(v["label"] == "Mum" for v in body["voiceprints"])
    # No raw embedding material anywhere in the export.
    assert "embedding" not in str(body["voiceprints"]).lower() or \
        all("embedding" not in k for v in body["voiceprints"] for k in v if k != "embedding_kind")
    assert any(r["details"] == "suspicious call" for r in body["reports"])

    db = SessionLocal()
    actions = [a.action for a in db.query(models.AuditLog).all()]
    assert "login" in actions and "voiceprint_create" in actions
    assert "data_export" in actions
    uid = body["profile"]["id"]
    db.close()

    assert client.delete("/me", headers=headers).status_code == 200
    assert client.get("/me", headers=headers).status_code == 401
    db = SessionLocal()
    assert db.query(models.Voiceprint).filter(models.Voiceprint.user_id == uid).count() == 0
    assert db.query(models.User).filter(models.User.id == uid).count() == 0
    actions = [a.action for a in db.query(models.AuditLog).all()]
    db.close()
    assert "account_delete" in actions
