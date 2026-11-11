from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, models
from ..db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RequestOtp(BaseModel):
    email: str


class VerifyOtp(BaseModel):
    email: str
    code: str
    name: str | None = None


@router.post("/request-otp")
def request_otp(body: RequestOtp, db: Session = Depends(get_db)):
    if "@" not in body.email:
        return {"ok": False, "detail": "Invalid email"}
    auth.request_otp(db, body.email)
    # The code itself is delivered out-of-band (email in production,
    # server log in DEV_MODE). It is never part of this response.
    return {"ok": True, "detail": "Code sent"}


@router.post("/verify-otp")
def verify_otp(body: VerifyOtp, db: Session = Depends(get_db)):
    user = auth.verify_otp(db, body.email, body.code)
    if body.name and not user.name:
        user.name = body.name
        db.commit()
    return {"ok": True, "token": auth.make_token(user),
            "user": {"id": user.id, "email": user.email, "name": user.name,
                     "language": user.language}}
