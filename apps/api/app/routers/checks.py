from __future__ import annotations

import secrets

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     UploadFile)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ml_inference import TARGET_SR, analyze, load_audio
from voiceprint import cosine, embed, from_bytes

from .. import models
from ..analysis import check_to_dict, refusion, run_analysis, _raise_alerts
from ..auth import get_current_user
from ..config import MAX_CLIP_SECONDS, MAX_UPLOAD_BYTES, VOICEPRINT_THRESHOLD
from ..db import get_db
from ..fusion import fuse
import json

router = APIRouter(prefix="/checks", tags=["checks"])

PHRASES = [
    "the blue umbrella is near the river",
    "my bicycle has a silver bell",
    "the mango tree flowers in march",
    "trains leave the old station at dawn",
    "the red kite is above the school",
]


def _own_check(db: Session, user: models.User, check_id: int) -> models.Check:
    c = db.get(models.Check, check_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "Check not found")
    return c


def _get_vp(db: Session, user: models.User, vp_id: int | None) -> models.Voiceprint | None:
    if vp_id is None:
        return None
    vp = db.get(models.Voiceprint, vp_id)
    if vp is None or vp.user_id != user.id:
        raise HTTPException(404, "Voiceprint not found")
    return vp


async def _decode(file: UploadFile):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Audio too large")
    try:
        samples, sr = load_audio(data, file.filename or "audio.wav")
    except Exception:
        raise HTTPException(400, "Could not decode audio")
    max_len = MAX_CLIP_SECONDS * sr
    return samples[:max_len], sr


@router.post("/clip")
async def check_clip(file: UploadFile = File(...),
                     voiceprint_id: int | None = Form(None),
                     user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    vp = _get_vp(db, user, voiceprint_id)
    samples, sr = await _decode(file)
    check = models.Check(user_id=user.id, type="clip",
                         voiceprint_id=vp.id if vp else None)
    db.add(check)
    db.commit()
    db.refresh(check)
    run_analysis(db, check, samples, sr, vp)
    return check_to_dict(check)


@router.get("/{check_id}")
def get_check(check_id: int, user: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    return check_to_dict(_own_check(db, user, check_id))


@router.get("")
def list_checks(user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rows = (db.query(models.Check).filter(models.Check.user_id == user.id)
            .order_by(models.Check.id.desc()).limit(50).all())
    return [check_to_dict(c) for c in rows]


# ------------------------------------------------------------------ live
class LiveStart(BaseModel):
    voiceprint_id: int | None = None


@router.post("/live/start")
def live_start(body: LiveStart, user: models.User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    vp = _get_vp(db, user, body.voiceprint_id)
    check = models.Check(user_id=user.id, type="live", status="open",
                         voiceprint_id=vp.id if vp else None)
    db.add(check)
    db.commit()
    db.refresh(check)
    return {"check_id": check.id, "status": "open"}


@router.post("/{check_id}/windows")
async def live_window(check_id: int, file: UploadFile = File(...),
                      user: models.User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Append one recorded chunk (the web client sends ~4 s WAV chunks)
    to an open live check and return the running fused verdict."""
    check = _own_check(db, user, check_id)
    if check.status != "open":
        raise HTTPException(400, "Live check is closed")
    samples, sr = await _decode(file)
    result = analyze(samples, sr)
    offset = max((w.t_end for w in check.windows), default=0.0)
    base_idx = max((w.idx for w in check.windows), default=-1) + 1
    for i, w in enumerate(result["windows"]):
        db.add(models.CheckWindow(
            check_id=check.id, idx=base_idx + i,
            t_start=offset + w["t_start"], t_end=offset + w["t_end"],
            spoof_score=w["spoof_score"]))
    db.commit()
    db.refresh(check)

    # Running verdict from all windows so far; voiceprint similarity is
    # computed once at finish (embedding a partial stream is noisy).
    scores = [w.spoof_score for w in sorted(check.windows, key=lambda x: x.idx)]
    fusion = fuse(scores, check.voiceprint_similarity, VOICEPRINT_THRESHOLD)
    return {"check_id": check.id, "windows_total": len(scores),
            "running_verdict": fusion.verdict,
            "running_risk": fusion.risk_score,
            "latest_window": result["windows"][-1] if result["windows"] else None}


@router.post("/{check_id}/finish")
async def live_finish(check_id: int,
                      file: UploadFile | None = File(None),
                      user: models.User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Close a live check. Optionally accepts the full-session recording
    for the final voiceprint comparison; otherwise the verdict is fused
    from spoof windows only."""
    check = _own_check(db, user, check_id)
    if check.status != "open":
        return check_to_dict(check)
    similarity = None
    if file is not None and check.voiceprint_id:
        vp = db.get(models.Voiceprint, check.voiceprint_id)
        samples, sr = await _decode(file)
        emb = embed(samples[:60 * sr], sr)
        similarity = round(cosine(from_bytes(vp.embedding), emb), 4)
        check.voiceprint_similarity = similarity
    scores = [w.spoof_score for w in sorted(check.windows, key=lambda x: x.idx)]
    fusion = fuse(scores, similarity, VOICEPRINT_THRESHOLD)
    check.verdict = fusion.verdict
    check.risk_score = fusion.risk_score
    check.aggregate_spoof = (round(sum(s for s in scores if s is not None) /
                                   max(1, sum(1 for s in scores if s is not None)), 4)
                             if any(s is not None for s in scores) else None)
    check.reasons_json = json.dumps(fusion.reasons)
    check.status = "complete"
    check.model_version = "baseline-heuristic-v0"
    db.commit()
    db.refresh(check)
    if fusion.verdict == "red":
        _raise_alerts(db, check)
    return check_to_dict(check)


# -------------------------------------------------------------- challenge
class ChallengeReq(BaseModel):
    kind: str = "liveness_phrase"  # liveness_phrase | code_word


class ChallengeVerify(BaseModel):
    passed: bool


@router.post("/{check_id}/challenge")
def issue_challenge(check_id: int, body: ChallengeReq,
                    user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    check = _own_check(db, user, check_id)
    if body.kind == "code_word":
        prompt = "Ask the caller: what is our family code word?"
    else:
        prompt = f"Ask the caller to say, right now: \u201c{secrets.choice(PHRASES)}\u201d"
    ch = models.Challenge(check_id=check.id, kind=body.kind, prompt=prompt)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return {"challenge_id": ch.id, "kind": ch.kind, "prompt": ch.prompt}


@router.post("/{check_id}/challenge/verify")
def verify_challenge(check_id: int, body: ChallengeVerify,
                     user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Record the challenge outcome and re-fuse the verdict.

    NOTE: in this build the outcome is attested by the user (they heard
    the caller say the phrase / give the code word). Server-side ASR
    verification is future work — the record states exactly who attested.
    """
    check = _own_check(db, user, check_id)
    ch = (db.query(models.Challenge)
          .filter(models.Challenge.check_id == check.id,
                  models.Challenge.result.is_(None))
          .order_by(models.Challenge.id.desc()).first())
    if ch is None:
        raise HTTPException(404, "No open challenge for this check")
    ch.result = "passed" if body.passed else "failed"
    db.commit()
    if check.status == "complete":
        refusion(db, check, ch.result)
    return {"ok": True, "result": ch.result,
            "check": check_to_dict(check)}
