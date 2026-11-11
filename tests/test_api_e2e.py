"""End-to-end API tests: auth -> enroll -> clip check -> circle -> report.

OTP codes are read from the test database directly (test-only access);
the API itself never returns them.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app import models
from conftest import synth_voice_bytes

client = TestClient(app)


def _login_with_known_code(email: str, code: str = "424242") -> dict:
    import datetime as dt
    import hashlib
    db = SessionLocal()
    db.add(models.OtpCode(
        email=email, code_hash=hashlib.sha256(code.encode()).hexdigest(),
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)))
    db.commit()
    db.close()
    r = client.post("/auth/verify-otp", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def auth() -> dict:
    return _login_with_known_code("parent@example.in")


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def _enroll(auth) -> int:
    files = [("samples", (f"s{i}.wav", synth_voice_bytes(4.0, seed=i), "audio/wav"))
             for i in range(3)]
    r = client.post("/voiceprints", headers=auth,
                    data={"label": "Son"}, files=files)
    assert r.status_code == 200, r.text
    vp = r.json()
    assert vp["label"] == "Son" and vp["sample_count"] == 3
    rows = client.get("/voiceprints", headers=auth).json()
    assert any(v["id"] == vp["id"] for v in rows)
    return vp["id"]


def test_enroll_and_list_voiceprint(auth):
    _enroll(auth)


def test_clip_check_end_to_end(auth):
    vp_id = _enroll(auth)
    clip = synth_voice_bytes(9.0, seed=7)
    r = client.post("/checks/clip", headers=auth,
                    data={"voiceprint_id": vp_id},
                    files={"file": ("call.wav", clip, "audio/wav")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] in ("green", "yellow", "red")
    assert len(body["windows"]) >= 2
    assert all("spoof_score" in w for w in body["windows"])
    assert body["voiceprint_similarity"] is not None
    assert body["reasons"], "verdict must carry plain-language reasons"
    got = client.get(f"/checks/{body['id']}", headers=auth)
    assert got.status_code == 200 and got.json()["id"] == body["id"]


def test_circle_invite_and_join(auth):
    r = client.post("/circles", headers=auth, json={"name": "Family"})
    assert r.status_code == 200
    cid = r.json()["id"]
    inv = client.post(f"/circles/{cid}/invite", headers=auth,
                      json={"email": "son@example.in"})
    assert inv.status_code == 200
    code = inv.json()["invite_code"]
    other = _login_with_known_code("son@example.in", code="313131")
    joined = client.post("/circles/join", headers=other, json={"code": code})
    assert joined.status_code == 200 and joined.json()["circle_id"] == cid
    circles = client.get("/circles", headers=other).json()
    assert any(c["id"] == cid for c in circles)


def test_report_and_alerts(auth):
    r = client.post("/reports", headers=auth,
                    json={"details": "Caller asked for money urgently"})
    assert r.status_code == 200
    rows = client.get("/reports", headers=auth).json()
    assert any(x["details"].startswith("Caller asked") for x in rows)
    assert isinstance(client.get("/me/alerts", headers=auth).json(), list)


def test_unauthenticated_rejected():
    assert client.get("/voiceprints").status_code == 401
    assert client.get("/me").status_code == 401
