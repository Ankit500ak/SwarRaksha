# SwarRaksha

**Every voice, verified.**

SwarRaksha is a real-time AI shield against **voice-clone scam calls**. It listens to a live call (or any audio clip), detects the artefacts that AI voice-cloning tools leave behind, verifies the caller against a trusted voiceprint, and warns the user *before* money changes hands.

> *Swar* = voice · *Raksha* = protection.

## The problem

Scammers now clone a family member's voice from a few seconds of social-media audio and call their parents: *"Maa, I'm in trouble, send money."* The voice sounds perfect to a human ear. It does not sound perfect to a model trained to hear synthesis artefacts.

## What it does

1. **Detect** — a streaming anti-spoofing model scores every few seconds of audio: human or synthetic?
2. **Verify** — the caller's voice is matched against enrolled voiceprints of your trusted contacts.
3. **Challenge** — when risk is high, SwarRaksha asks a live liveness challenge only the real person can pass, or prompts for the family code word.
4. **Verdict** — one clear screen: 🟢 Voice verified · 🟡 Unverified — be careful · 🔴 Likely cloned voice — do not send money.

## Status

🚧 MVP built and running locally (Nov 2026). The complete production plan — architecture, ML pipeline, data strategy, API design, milestones — lives in **[PLAN.md](PLAN.md)**.

**Honest build note:** the shipped detector is `baseline-heuristic-v0` — an *untrained* rule-based scorer over acoustic features, and speaker verification is an MFCC-statistics baseline. They wire the full product end-to-end and are documented, with limits, in **[services/ml-inference/MODEL_CARD.md](services/ml-inference/MODEL_CARD.md)**. No benchmark accuracy is claimed. The trained AASIST + ECAPA-TDNN models are the roadmap in PLAN.md §6.

## Run it locally

```bash
make setup   # one-time: python venv + web dependencies
make dev     # API on http://localhost:8000, web on http://localhost:5173
make test    # pytest suite (fusion unit tests + API end-to-end)
```

Sign-in is email-OTP; in this local dev mode (`SWAR_DEV_MODE=1`) the code is printed in the API server log — never in an API response. Full stack via Docker: `infra/docker/docker-compose.yml`.

Layout: `apps/api` (FastAPI) · `apps/web` (React+Vite+TS) · `services/ml-inference` (detector, importable package + standalone HTTP service) · `services/voiceprint` (speaker embedding baseline) · `tests/` · `infra/docker/`.

## Planned stack

- **ML**: PyTorch anti-spoofing (AASIST-class) + ECAPA-TDNN speaker embeddings, exported to ONNX for streaming inference
- **Backend**: FastAPI, WebSocket audio streaming, PostgreSQL, Redis
- **Frontend**: React (web app first), React Native later
- **Infra**: Docker, GitHub Actions CI, Render/Fly.io + Vercel

## Privacy first

Voiceprints are stored as **embeddings, never raw audio**. Analysis is consent-based, recordings are not retained by default, and all personal data handling is designed around India's DPDP Act principles.

## Author

**Ankit Pal** — B.Tech CSE (AI & ML), 2026 · [GitHub](https://github.com/Ankit500ak) · [LinkedIn](https://www.linkedin.com/in/ankitpalbuilds)
