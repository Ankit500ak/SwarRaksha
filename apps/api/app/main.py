"""SwarRaksha API — FastAPI application.

Local run (from repo root):
  PYTHONPATH=services/ml-inference:services/voiceprint:apps/api \
  SWAR_DEV_MODE=1 .venv/bin/uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ml_inference import MODEL_VERSION

from .config import DEV_MODE
from .db import init_db
from .routers import auth_routes, checks, circles, me, reports, voiceprints

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SwarRaksha API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

init_db()

app.include_router(auth_routes.router)
app.include_router(voiceprints.router)
app.include_router(circles.router)
app.include_router(checks.router)
app.include_router(reports.router)
app.include_router(me.router)


@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION,
            "dev_mode": DEV_MODE}
