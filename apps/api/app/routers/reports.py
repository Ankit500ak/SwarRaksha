from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..db import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReport(BaseModel):
    check_id: int | None = None
    details: str = ""


@router.post("")
def create_report(body: CreateReport, user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    r = models.Report(user_id=user.id, check_id=body.check_id, details=body.details)
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None}


@router.get("")
def list_reports(user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    rows = (db.query(models.Report).filter(models.Report.user_id == user.id)
            .order_by(models.Report.id.desc()).limit(50).all())
    return [{"id": r.id, "check_id": r.check_id, "details": r.details,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]
