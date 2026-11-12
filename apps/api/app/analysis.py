"""Shared check-analysis pipeline: audio -> windows -> voiceprint ->
fusion -> persisted verdict (+ family alerts on RED)."""
from __future__ import annotations

import json

import numpy as np
from sqlalchemy.orm import Session

from ml_inference import analyze
from voiceprint import cosine, embed, from_bytes

from . import models
from .config import VOICEPRINT_THRESHOLD
from .encryption import decrypt_embedding
from .fusion import fuse


def run_analysis(db: Session, check: models.Check, samples: np.ndarray,
                 sr: int, voiceprint: models.Voiceprint | None) -> models.Check:
    result = analyze(samples, sr)
    for w in result["windows"]:
        db.add(models.CheckWindow(
            check_id=check.id, idx=w["index"], t_start=w["t_start"],
            t_end=w["t_end"], spoof_score=w["spoof_score"]))
    check.aggregate_spoof = result["aggregate_spoof"]
    check.model_version = result["model_version"]

    similarity = None
    if voiceprint is not None:
        # Verify against up to the first 60 s of audio.
        emb = embed(samples[:60 * sr], sr)
        similarity = round(cosine(from_bytes(decrypt_embedding(voiceprint.embedding)), emb), 4)
        check.voiceprint_similarity = similarity

    scores = [w["spoof_score"] for w in result["windows"]]
    fusion = fuse(scores, similarity, VOICEPRINT_THRESHOLD)
    check.verdict = fusion.verdict
    check.risk_score = fusion.risk_score
    check.reasons_json = json.dumps(fusion.reasons)
    check.status = "complete"
    db.commit()
    db.refresh(check)
    if fusion.verdict == "red":
        _raise_alerts(db, check)
    return check


def refusion(db: Session, check: models.Check,
             challenge_result: str | None) -> models.Check:
    """Recompute a check's verdict from stored windows (e.g. after a
    challenge result arrives)."""
    windows = sorted(check.windows, key=lambda w: w.idx)
    scores = [w.spoof_score for w in windows]
    fusion = fuse(scores, check.voiceprint_similarity, VOICEPRINT_THRESHOLD,
                  challenge_result=challenge_result)
    check.verdict = fusion.verdict
    check.risk_score = fusion.risk_score
    check.reasons_json = json.dumps(fusion.reasons)
    db.commit()
    db.refresh(check)
    if fusion.verdict == "red":
        _raise_alerts(db, check)
    return check


def _raise_alerts(db: Session, check: models.Check) -> None:
    """Notify the checker and their circle co-members about a RED verdict
    (PLAN.md v1.0 alert behaviour, pulled into this build)."""
    label = "an enrolled voice" if check.voiceprint_id else "a caller"
    msg = (f"SwarRaksha alert: a check by a family member returned LIKELY CLONED "
           f"for {label}. Do not send money; call back on the saved number.")
    recipient_ids = {check.user_id}
    memberships = (db.query(models.CircleMember)
                   .filter(models.CircleMember.user_id == check.user_id,
                           models.CircleMember.status == "active").all())
    circle_ids = {m.circle_id for m in memberships}
    if circle_ids:
        peers = (db.query(models.CircleMember)
                 .filter(models.CircleMember.circle_id.in_(circle_ids),
                         models.CircleMember.status == "active",
                         models.CircleMember.user_id.isnot(None)).all())
        recipient_ids |= {p.user_id for p in peers}
    for uid in recipient_ids:
        db.add(models.Alert(user_id=uid, check_id=check.id, message=msg))
    db.commit()


def check_to_dict(check: models.Check) -> dict:
    windows = sorted(check.windows, key=lambda w: w.idx)
    return {
        "id": check.id,
        "type": check.type,
        "status": check.status,
        "voiceprint_id": check.voiceprint_id,
        "verdict": check.verdict,
        "risk_score": check.risk_score,
        "aggregate_spoof": check.aggregate_spoof,
        "voiceprint_similarity": check.voiceprint_similarity,
        "model_version": check.model_version,
        "reasons": json.loads(check.reasons_json or "[]"),
        "windows": [{"index": w.idx, "t_start": w.t_start, "t_end": w.t_end,
                     "spoof_score": w.spoof_score} for w in windows],
        "created_at": check.created_at.isoformat() if check.created_at else None,
    }
