"""Audit-log writes (PLAN.md §8). NEVER log audio or embedding bytes —
only actor, action, target identifiers and timestamps."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from . import models

log = logging.getLogger("swarraksha.audit")


def write_audit(db: Session, actor_id: int | None, action: str,
                target: str = "") -> None:
    """Append an audit row. Caller owns the surrounding transaction in
    most flows; we commit here so the record survives e.g. account
    deletion, where the actor row itself is about to disappear."""
    db.add(models.AuditLog(actor_id=actor_id, action=action, target=str(target)))
    db.commit()
    log.info("audit actor=%s action=%s target=%s", actor_id, action, target)
