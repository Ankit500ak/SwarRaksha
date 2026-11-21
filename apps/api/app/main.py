"""SwarRaksha API — FastAPI application.

Local run (from repo root):
  PYTHONPATH=services/ml-inference:services/voiceprint:apps/api \
  SWAR_DEV_MODE=1 .venv/bin/uvicorn app.main:app --port 8000

Production (SWAR_ENV=production) refuses to boot on unsafe config —
see config.validate_config.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ml_inference import MODEL_VERSION

from . import config
from .config import DEV_MODE
from .db import SessionLocal, init_db
from .ratelimit import limiter
from .routers import auth_routes, checks, circles, me, reports, voiceprints

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("swarraksha.api")

# Fail closed in production before anything else is wired up.
_prod_errors = config.validate_config()
if _prod_errors:
    for _e in _prod_errors:
        log.error("production config: %s", _e)
    raise RuntimeError("Refusing to boot with unsafe production config: "
                       + "; ".join(_prod_errors))

app = FastAPI(title="SwarRaksha API", version="0.1.0")

app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                   allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"])

_STATUS_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden",
                 404: "not_found", 409: "conflict", 413: "payload_too_large",
                 422: "validation_error", 429: "rate_limited",
                 503: "unavailable"}


def error_body(status: int, message: str) -> dict:
    return {"code": _STATUS_CODES.get(status, "error" if status < 500 else "internal_error"),
            "message": message}


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(status_code=exc.status_code,
                        content=error_body(exc.status_code, detail))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422,
                        content={"code": "validation_error",
                                 "message": "Request validation failed"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500,
                        content={"code": "internal_error",
                                 "message": "Internal server error"})


@app.middleware("http")
async def security_and_limits(request: Request, call_next):
    # Request-size cap.
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > config.MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413,
                                    content=error_body(413, "Request too large"))
        except ValueError:
            pass
    # Per-IP rate limiting: stricter buckets for auth and clip checks.
    ip = request.client.host if request.client else "unknown"
    path = request.url.path
    if path.startswith("/auth/"):
        bucket, limit = "auth", config.RATE_LIMIT_AUTH_PER_MIN
    elif path.startswith("/checks/clip") or path.endswith("/windows"):
        bucket, limit = "clip", config.RATE_LIMIT_CLIP_PER_MIN
    else:
        bucket, limit = "global", config.RATE_LIMIT_GLOBAL_PER_MIN
    if not limiter.allow(bucket, ip, limit):
        return JSONResponse(status_code=429,
                            content=error_body(429, "Too many requests; slow down"))
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Cache-Control"] = "no-store"
    return response


init_db()

app.include_router(auth_routes.router)
app.include_router(voiceprints.router)
app.include_router(circles.router)
app.include_router(checks.router)
app.include_router(reports.router)
app.include_router(me.router)

# Exposed for tests / ops introspection.
app.state.rate_limiter = limiter


@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION,
            "dev_mode": DEV_MODE, "env": config.SWAR_ENV}


@app.get("/ready")
def ready():
    """Readiness: DB connectivity + (in production) config sanity."""
    errors = config.validate_config()
    db_ok = True
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        db_ok = False
    if not db_ok or errors:
        return JSONResponse(status_code=503,
                            content={"code": "unavailable",
                                     "message": "Not ready",
                                     "db_ok": db_ok, "config_errors": errors})
    return {"status": "ready", "db_ok": True}
