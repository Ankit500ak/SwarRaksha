from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..db import get_db

router = APIRouter(prefix="/circles", tags=["circles"])


class CreateCircle(BaseModel):
    name: str


class Invite(BaseModel):
    email: str


class Join(BaseModel):
    code: str


def _circle_dict(db: Session, c: models.Circle) -> dict:
    members = []
    for m in c.members:
        email = None
        if m.user_id:
            u = db.get(models.User, m.user_id)
            email = u.email if u else None
        members.append({"user_id": m.user_id, "email": email or m.invited_email,
                        "role": m.role, "status": m.status})
    return {"id": c.id, "name": c.name, "owner_id": c.owner_id, "members": members}


@router.post("")
def create_circle(body: CreateCircle, user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    c = models.Circle(owner_id=user.id, name=body.name)
    db.add(c)
    db.flush()
    db.add(models.CircleMember(circle_id=c.id, user_id=user.id,
                               role="owner", status="active"))
    db.commit()
    db.refresh(c)
    return _circle_dict(db, c)


@router.get("")
def list_circles(user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    mine = (db.query(models.CircleMember)
            .filter(models.CircleMember.user_id == user.id,
                    models.CircleMember.status == "active").all())
    return [_circle_dict(db, db.get(models.Circle, m.circle_id)) for m in mine]


@router.post("/{circle_id}/invite")
def invite(circle_id: int, body: Invite,
           user: models.User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    c = db.get(models.Circle, circle_id)
    if c is None or c.owner_id != user.id:
        raise HTTPException(404, "Circle not found or not yours")
    code = uuid.uuid4().hex
    db.add(models.CircleMember(circle_id=c.id, invited_email=body.email.lower(),
                               invite_code=code, status="invited"))
    db.commit()
    # The invite code is the accept-by-link credential for this circle;
    # share it with the invited person out-of-band.
    return {"ok": True, "invite_code": code,
            "join_path": f"/circles/join?code={code}"}


@router.post("/join")
def join(body: Join, user: models.User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    m = (db.query(models.CircleMember)
         .filter(models.CircleMember.invite_code == body.code,
                 models.CircleMember.status == "invited").first())
    if m is None:
        raise HTTPException(404, "Invite not found or already used")
    if m.invited_email and m.invited_email != user.email:
        raise HTTPException(403, "This invite was issued to a different email")
    m.user_id = user.id
    m.status = "active"
    m.invite_code = None
    db.commit()
    return {"ok": True, "circle_id": m.circle_id}
