from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..db import get_db

router = APIRouter(prefix="/me", tags=["me"])


class UpdateMe(BaseModel):
    name: str | None = None
    language: str | None = None


@router.get("")
def me(user: models.User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name,
            "language": user.language}


@router.patch("")
def update_me(body: UpdateMe, user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name
    if body.language in ("en", "hi"):
        user.language = body.language
    db.commit()
    return {"id": user.id, "email": user.email, "name": user.name,
            "language": user.language}


@router.get("/alerts")
def alerts(user: models.User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    rows = (db.query(models.Alert).filter(models.Alert.user_id == user.id)
            .order_by(models.Alert.id.desc()).limit(50).all())
    return [{"id": a.id, "check_id": a.check_id, "message": a.message,
             "read": a.read,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in rows]


@router.post("/alerts/{alert_id}/read")
def mark_read(alert_id: int, user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    a = db.get(models.Alert, alert_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Alert not found")
    a.read = True
    db.commit()
    return {"ok": True}
