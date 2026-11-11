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

🚧 In active development. The complete production plan — architecture, ML pipeline, data strategy, API design, milestones — lives in **[PLAN.md](PLAN.md)**.

## Planned stack

- **ML**: PyTorch anti-spoofing (AASIST-class) + ECAPA-TDNN speaker embeddings, exported to ONNX for streaming inference
- **Backend**: FastAPI, WebSocket audio streaming, PostgreSQL, Redis
- **Frontend**: React (web app first), React Native later
- **Infra**: Docker, GitHub Actions CI, Render/Fly.io + Vercel

## Privacy first

Voiceprints are stored as **embeddings, never raw audio**. Analysis is consent-based, recordings are not retained by default, and all personal data handling is designed around India's DPDP Act principles.

## Author

**Ankit Pal** — B.Tech CSE (AI & ML), 2026 · [GitHub](https://github.com/Ankit500ak) · [LinkedIn](https://www.linkedin.com/in/ankitpalbuilds)
