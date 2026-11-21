from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit, models
from ..analysis import check_to_dict
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


# ------------------------------------------------------------- privacy
@router.get("/export")
def export_data(user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Download everything we hold about the user (DPDP data export).

    Deliberately EXCLUDED, by design: raw voiceprint embedding bytes
    (biometric secrets — exporting them would defeat encryption at rest;
    metadata such as label/kind/dates is included), OTP hashes, other
    users' data, and internal audit internals beyond the user's own
    actions.
    """
    vps = (db.query(models.Voiceprint)
           .filter(models.Voiceprint.user_id == user.id).all())
    checks = (db.query(models.Check)
              .filter(models.Check.user_id == user.id).all())
    reports = (db.query(models.Report)
               .filter(models.Report.user_id == user.id).all())
    memberships = (db.query(models.CircleMember)
                   .filter(models.CircleMember.user_id == user.id).all())
    my_alerts = (db.query(models.Alert)
                 .filter(models.Alert.user_id == user.id).all())
    data = {
        "profile": {"id": user.id, "email": user.email, "name": user.name,
                    "language": user.language,
                    "created_at": user.created_at.isoformat() if user.created_at else None},
        "voiceprints": [{"id": v.id, "label": v.label,
                         "embedding_kind": v.embedding_kind,
                         "sample_count": v.sample_count,
                         "consent_at": v.consent_at.isoformat() if v.consent_at else None,
                         "created_at": v.created_at.isoformat() if v.created_at else None}
                        for v in vps],
        "checks": [check_to_dict(c) for c in checks],
        "reports": [{"id": r.id, "check_id": r.check_id, "details": r.details,
                     "created_at": r.created_at.isoformat() if r.created_at else None}
                    for r in reports],
        "circles": [{"circle_id": m.circle_id, "role": m.role, "status": m.status}
                    for m in memberships],
        "alerts": [{"id": a.id, "check_id": a.check_id, "message": a.message,
                    "read": a.read,
                    "created_at": a.created_at.isoformat() if a.created_at else None}
                   for a in my_alerts],
    }
    audit.write_audit(db, user.id, "data_export", f"user:{user.id}")
    return data


@router.delete("")
def delete_account(user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Hard-delete the account and everything attached to it: voiceprints
    (embeddings wiped), checks + windows + challenges, reports, alerts,
    circle memberships and owned circles, and outstanding OTP codes.
    The audit record of the deletion itself is kept (actor id only)."""
    uid, email = user.id, user.email
    check_ids = [c.id for c in db.query(models.Check)
                 .filter(models.Check.user_id == uid).all()]
    if check_ids:
        db.query(models.Challenge).filter(
            models.Challenge.check_id.in_(check_ids)).delete(synchronize_session=False)
        db.query(models.CheckWindow).filter(
            models.CheckWindow.check_id.in_(check_ids)).delete(synchronize_session=False)
    db.query(models.Check).filter(models.Check.user_id == uid).delete(synchronize_session=False)
    db.query(models.Voiceprint).filter(models.Voiceprint.user_id == uid).delete(synchronize_session=False)
    db.query(models.Report).filter(models.Report.user_id == uid).delete(synchronize_session=False)
    db.query(models.Alert).filter(models.Alert.user_id == uid).delete(synchronize_session=False)
    owned = [c.id for c in db.query(models.Circle).filter(models.Circle.owner_id == uid).all()]
    if owned:
        db.query(models.CircleMember).filter(
            models.CircleMember.circle_id.in_(owned)).delete(synchronize_session=False)
        db.query(models.Circle).filter(models.Circle.id.in_(owned)).delete(synchronize_session=False)
    db.query(models.CircleMember).filter(models.CircleMember.user_id == uid).delete(synchronize_session=False)
    db.query(models.OtpCode).filter(models.OtpCode.email == email).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.id == uid).delete(synchronize_session=False)
    db.commit()
    audit.write_audit(db, uid, "account_delete", f"user:{uid}")
    return {"ok": True}
