from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ml_inference import load_audio
from voiceprint import enroll, to_bytes, EMBEDDING_KIND

from .. import audit, models
from ..auth import get_current_user
from ..db import get_db
from ..encryption import encrypt_embedding
from ..uploads import validate_audio

router = APIRouter(prefix="/voiceprints", tags=["voiceprints"])


def _public(vp: models.Voiceprint) -> dict:
    return {"id": vp.id, "label": vp.label, "embedding_kind": vp.embedding_kind,
            "sample_count": vp.sample_count,
            "created_at": vp.created_at.isoformat() if vp.created_at else None}


@router.post("")
async def create_voiceprint(label: str = Form(...),
                            samples: list[UploadFile] = File(...),
                            user: models.User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Enroll a voiceprint from exactly 3 audio samples.

    Consent: the enrollment is recorded with a timestamp. Enrolling
    someone else's voice requires their consent (PLAN.md Section 11) —
    the product flow asks for it; the API records that it was given.
    """
    if len(samples) != 3:
        raise HTTPException(400, "Exactly 3 samples are required for enrollment")
    arrays = []
    for s in samples:
        data = await s.read()
        validate_audio(data, s.filename)
        try:
            arr, sr = load_audio(data, s.filename or "sample.wav")
        except Exception:
            raise HTTPException(400, f"Could not decode audio sample {s.filename}")
        if len(arr) < sr * 2:
            raise HTTPException(400, "Each sample must be at least 2 seconds of speech")
        arrays.append(arr)
    vec = enroll(arrays, sr)
    vp = models.Voiceprint(user_id=user.id, label=label,
                           embedding=encrypt_embedding(to_bytes(vec)),
                           embedding_kind=EMBEDDING_KIND,
                           sample_count=3)
    db.add(vp)
    db.commit()
    db.refresh(vp)
    audit.write_audit(db, user.id, "voiceprint_create", f"voiceprint:{vp.id}")
    return _public(vp)


@router.get("")
def list_voiceprints(user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    rows = (db.query(models.Voiceprint)
            .filter(models.Voiceprint.user_id == user.id)
            .order_by(models.Voiceprint.id).all())
    return [_public(v) for v in rows]


@router.delete("/{vp_id}")
def delete_voiceprint(vp_id: int, user: models.User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    vp = db.get(models.Voiceprint, vp_id)
    if vp is None or vp.user_id != user.id:
        raise HTTPException(404, "Voiceprint not found")
    db.delete(vp)
    db.commit()
    audit.write_audit(db, user.id, "voiceprint_delete", f"voiceprint:{vp_id}")
    return {"ok": True}
