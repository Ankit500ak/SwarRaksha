"""Standalone ML inference service (FastAPI).

The API service imports the ml_inference package directly for the local
build; this app exposes the same detector over HTTP for the Docker /
multi-service deployment described in PLAN.md Section 5.

Run: uvicorn ml_inference.app:app --port 8001
"""
from __future__ import annotations

from fastapi import FastAPI, File, UploadFile

from .audio_io import load_audio
from .detector import analyze, MODEL_VERSION

app = FastAPI(title="SwarRaksha ML Inference", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION,
            "model_kind": "untrained heuristic baseline — see MODEL_CARD.md"}


@app.post("/score")
async def score(file: UploadFile = File(...)):
    data = await file.read()
    samples, sr = load_audio(data, file.filename or "audio.wav")
    return analyze(samples, sr)
