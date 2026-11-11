# SwarRaksha — local development
# One-time setup:  make setup
# Run everything:  make dev        (API on :8000, web on :5173)
# Run tests:       make test

PY := .venv/bin/python
export PYTHONPATH := services/ml-inference:services/voiceprint:apps/api
export SWAR_DEV_MODE ?= 1

.PHONY: setup api web dev test ml

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q numpy scipy soundfile fastapi "uvicorn[standard]" sqlalchemy pyjwt python-multipart pydantic pytest httpx
	cd apps/web && npm install --no-audit --no-fund

api:
	.venv/bin/uvicorn app.main:app --app-dir apps/api --port 8000

ml:
	.venv/bin/uvicorn ml_inference.app:app --port 8001

web:
	cd apps/web && npm run dev

dev:
	@echo "Starting API (:8000) and web (:5173). OTP codes appear in this log (DEV_MODE)."
	.venv/bin/uvicorn app.main:app --app-dir apps/api --port 8000 & \
	API_PID=$$!; \
	trap "kill $$API_PID" EXIT; \
	cd apps/web && npm run dev

test:
	.venv/bin/python -m pytest tests/ -q
