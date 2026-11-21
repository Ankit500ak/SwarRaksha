# SwarRaksha — AI Handoff Summary

## Project Overview
**Product:** SwarRaksha — real-time AI shield against voice-clone scam calls  
**Tagline:** Every voice, verified.  
**Owner:** Ankit Pal  
**Status:** Planning v1.0 · 11 Nov 2026  
**Repo:** github.com/Ankit500ak/SwarRaksha  

**Problem:** AI voice cloning needs only 3–10 seconds of audio to produce a near-perfect copy. Scammers use "family emergency" calls to trick victims into sending money. Humans cannot reliably hear the difference, but models can detect synthetic artifacts.

**Core Functions:**
1. **Detect** — anti-spoofing model analyses audio windows (2–4s), outputs synthetic probability
2. **Verify** — caller's voice embedding matched against enrolled voiceprints of trusted contacts
3. **Challenge** — when risk crosses threshold: liveness prompt (random phrase) or family code word
4. **Verdict** — one fused risk score → one screen: 🟢 Verified / 🟡 Unverified — be careful / 🔴 Likely cloned — do not send money

---

## PROJECT STRUCTURE

```
C:\Users\Admin\Desktop\SwarRaksha\
├── apps/api/              # FastAPI backend
├── apps/web/              # React + Vite frontend
├── services/ml-inference/ # ML anti-spoofing + voiceprint service
├── services/voiceprint/   # Speaker embedding baseline
├── tests/                 # pytest + vitest suite
├── infra/docker/          # Docker + docker-compose
├── Makefile
├── PLAN.md                # Complete production plan (258 lines)
└── README.md
```

---

## FRONTEND COMPONENTS (12 components)

### 1. Navigation Bar
- **6 tabs:** home | live | enroll | family | history | settings
- **Multilingual:** English (`en`) / Hindi (`hi`) labels
- **Behavior:** Tab buttons toggle active state; labels translated via `t(key, lang)`

### 2. Landing Screen (unauthenticated)
- **Hero section:** Problem statement + three verdict emojis (🟢 🟡 🔴)
- **Sign-in:** Email → OTP verification flow
- **Dev note:** "In this local dev build, the code is printed in the API server log"

### 3. Check Screen (clip upload/analysis)
- **Voice selector:** Dropdown of enrolled voiceprints + "No enrolled voice" option
- **File upload:** `<input type="file" accept="audio/*">` — up to ~2 minutes
- **Recorder:** "Record instead" uses `useRecorder` hook (16kHz mono WAV)
- **Analysis:** Spinner while API processes; renders VerdictView on completion

### 4. Live Screen (WebSocket streaming)
- **Voice selector:** Enrolled voiceprints dropdown
- **Start/Stop:** ▶ Start live check / ⏹ Stop & get verdict
- **Risk meter:** Large circular progress bar with real-time percentage
- **Window counter:** "windows heard: N" — counts 4-second analysis windows
- **Info text:** "Put the call on speaker — SwarRaksha listens in 4-second windows. It does not store the audio."

### 5. Enroll Screen (voiceprint wizard)
- **Label input:** "Whose voice? e.g. Son — Rohan"
- **3-sample recorder:** Each sample 5–10 seconds, quality feedback provided
- **Enroll button:** Disabled until all 3 samples recorded + label provided
- **Delete:** Per-enrolled voiceprint delete functionality

### 6. Family Screen (circle management)
- **Create circle:** Input name + button
- **Circle list:** Each shows name + member list + invite section
- **Invite flow:** Input email → "Invite" → shows join code for sharing
- **Join circle:** Input join code → "Join" button

### 7. History Screen (past checks)
- **Check list:** Each shows verdict emoji + type + date + risk percentage
- **View detail:** Opens full VerdictView modal for specific check
- **Mount:** `api.listChecks()` on component mount

### 8. Settings Screen (user controls)
- **Language toggle:** English / हिन्दी buttons (active state management)
- **Alerts:** List of alerts with "Mark read" buttons
- **User info:** "Signed in as {email}{name}"
- **Sign out:** Clears token, redirects to landing page

### 9. Verdict View (reusable component)
- **Verdict emoji:** 🟢 / 🟡 / 🔴 based on verdict value
- **Title:** Translated ("verified", "cloned", "unverified")
- **Risk meter:** Progress bar with `%` width
- **Reasons list:** `<ul>` of explanation reasons from API result
- **Advice:** Green/yellow/red "what to do next" text
- **Window bars:** Per-window spoof score bars (each = 4 seconds)
- **Challenge flow:** "Ask for code word" / "Give liveness phrase" → verify pass/fail
- **Report:** "Report scam attempt" → marks as reported ✓

### 10. useRecorder Hook
- **Purpose:** Browser audio recording capture
- **Returns:** `recRef`, `recording`, `start`, `stop` functions
- **Captures:** 16kHz mono WAV audio via `WavRecorder` browser API

### 11. App Shell
- **Structure:** Header + navigation + main (conditional screens) + footer
- **Footer:** "Baseline demo build — the detector is an untrained heuristic (see MODEL_CARD). Risk, never certainty."
- **Auth check:** `!authed` → Landing; `authed` → tabbed interface

### 12. i18n Text System
- **Language files:** `apps/web/src/i18n.ts`
- **Supported:** English (`en`), Hindi (`hi`)
- **Usage:** All labels, titles, advice use `t(key, lang)` function calls

---

## BACKEND API ENDPOINTS (v1)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/request-otp` | Send OTP for login |
| POST | `/auth/verify-otp` | Verify OTP, get JWT token |
| POST | `/voiceprints` | Enroll voiceprint (multipart audio ×3) |
| GET | `/voiceprints` | List voiceprints |
| DELETE | `/voiceprints/{id}` | Delete voiceprint (embedding + samples) |
| POST | `/circles` | Create family circle |
| POST | `/circles/{id}/invite` | Invite member to circle |
| POST | `/checks/clip` | Upload clip → check ID |
| GET | `/checks/{id}` | Get verdict, window scores, explanation |
| WSS | `/checks/live` | Streaming live check (audio chunks in, scores out) |
| POST | `/checks/{id}/challenge` | Issue/verify liveness challenge |
| POST | `/reports` | Report scam attempt |
| GET | `/me/alerts` | Family alerts |

---

## DATABASE CORE TABLES

- **users** (id, email, name, language, created_at)
- **circles** (id, owner_id, name)
- **circle_members** (circle_id, user_id, role)
- **voiceprints** (id, user_id, label, embedding_encrypted, sample_count, consent_at)
- **checks** (id, user_id, type[clip|live], verdict, risk_score, model_version, created_at)
- **check_windows** (check_id, t_start, spoof_score, spk_similarity)
- **challenges** (check_id, type, result)
- **reports** (id, user_id, details, created_at)
- **audit_log** (actor, action, target, at)

---

## ML MODEL SPECIFICATION

### Anti-spoofing Model (Model 1)
- **Architecture:** AASIST-class (spectro-temporal graph attention) or RawNet2
- **Output:** Probability window is synthetic (TTS / voice-conversion / replay)
- **Serving:** Exported to ONNX, quantised; target < 300 ms per 4s window on small CPU

### Speaker Verification (Model 2)
- **Architecture:** ECAPA-TDNN embeddings (SpeechBrain pretrained)
- **Embedding dim:** 192-dim voiceprint
- **Enrollment:** 3 samples × ~10 s → averaged embedding, stored encrypted
- **Matching:** cosine similarity vs. claimed identity; threshold start ~0.75

### Data Strategy
- **ASVspoof 2019/2021:** Core training/eval benchmark
- **Self-generated clones:** 10-15 consenting voices with written consent (key differentiator)
- **Hard negatives:** Phone-codec audio (8 kHz compressed), noisy rooms, elderly voices, emotional/crying speech
- **Indian-language:** Hindi/English code-mixed samples; Mozilla Common Voice Hindi

### Evaluation Targets
- **Anti-spoofing:** EER < 8% on self-generated set (MVP), < 5% (v1.0)
- **Verification:** FAR < 2% at chosen threshold
- **End-to-end:** 50 scripted scam calls + 50 genuine calls → public verdict accuracy

---

## INFRASTRUCTURE & DEVOPS

### Containers
- **One Dockerfile per service**
- **docker-compose.yml** runs whole stack locally (API + ML + Postgres + Redis)

### CI/CD
- **CI (GitHub Actions):** lint + type-check + unit tests on every PR
- **Model-eval smoke test** on model PRs
- **CD:** staging auto-deploys from `main`; production manual promote of same image

### Hosting (starting lean)
- **API + ML:** Single small VPS or Render/Fly
- **Web:** Vercel
- **PostgreSQL:** Managed service
- **Estimated cost:** ₹0–1,500/month on free/starter tiers

### Observability
- **Structured logs** (no audio, no embeddings in logs)
- **Health endpoints**
- **Latency dashboards**
- **Error tracking:** Sentry free tier
- **Backups:** daily DB backup, 7-day retention (voiceprint embeddings encrypted at rest)

---

## SECURITY & PRIVACY (non-negotiables)

- **Voiceprints:** Stored as encrypted embeddings; raw audio deleted after embedding
- **TLS everywhere:** JWT short-lived + refresh rotation; OTP rate-limited
- **Per-user rate limits** on checks (anti-abuse: prevent "free test my clone" service)
- **Consent-first:** Enrollment requires voice owner's OTP-verified session
- **DPDP Act alignment:** Purpose limitation, data-minimisation, erasure on request, breach-notification plan in `docs/privacy/`
- **Threat model:** Reviewed before v1.0 — attacker goals: test clones, steal voiceprints, social-engineering support

---

## MILESTONES & PHASES

### Phase 0 — Foundations (Days 1–3)
- Repo, CI, docker-compose stack up
- Download ASVspoof dataset
- Pretrained anti-spoof + SpeechBrain baselines running in notebooks
- **Exit:** notebook demo scores one real + one cloned clip correctly

### Phase 1 — Clip Check End-to-End (Week 1–2)
- FastAPI + inference service (ONNX)
- Upload/record UI, verdict screen
- Eval harness v1 with self-generated clone set (≥ 5 voices × 2 cloners)
- **Exit:** stranger can open site, upload clip, get correct explained verdict

### Phase 2 — Voiceprints & Family (Week 3)
- Enrollment wizard, verification in check flow
- Circles + invites, Hindi UI
- **Exit:** "This claims to be your son" flow works for enrolled family

### Phase 3 — Live Mode & Challenges (Week 4)
- WebSocket streaming, live risk meter
- Liveness prompts + code-word flow, alerts
- **Exit:** full demo scenario runs end-to-end → MVP ships

### Phase 4 — Production Hardening (Weeks 5–6)
- Load tests: 50 concurrent live streams
- Security review, privacy docs, observability
- Canary model deploy to 10% of checks, auto-rollback
- Landing page + demo video, beta with 5 real families
- **Exit:** v1.0 production release

### Phase 5 — v2 Exploration (post-launch)
- Android app with CallScreeningService exploration
- B2B API for banks/call centres (per-minute pricing)
- More languages: Tamil, Telugu, Bengali, Marathi
- On-device tiny model for offline clip checks
- Continuous model improvement from consented, anonymised reported scams

---

## EXPLICITLY OUT OF SCOPE

- Recording or storing calls by default (store embeddings + scores only)
- Identifying unknown people (only verifies against enrolled family voices with consent)
- Any claim of 100% accuracy (communicates risk, never certainty)

---

## KEY DECISIONS NEEDED

1. **Repo public from day one** (code only; never data, audio, or keys)
2. **First cloner tools** for self-generated set (pick 2 open-source tools)
3. **Beta families:** 3–5 real families willing to enroll and give feedback
4. **Name lock:** SwarRaksha · tagline "Every voice, verified" · repo Ankit500ak/SwarRaksha

---

## COPY-PASTE READY FOR AI

**Project:** SwarRaksha — voice clone scam detection  
**Goal:** Build AI system that detects synthesized voice audio and verifies against enrolled family voiceprints  
**Current state:** MVP built locally (Nov 2026), production plan in PLAN.md  
**Frontend:** React + Vite + TypeScript, 6 tabs (home/live/enroll/family/history/settings)  
**Backend:** FastAPI, WebSocket audio streaming, PostgreSQL + Redis  
**ML:** ONNX anti-spoofing + ECAPA-TDNN speaker embeddings  
**Key files to review:** 
- `PLAN.md` — full production plan (258 lines)
- `apps/web/src/App.tsx` — all 12 frontend components  
- `apps/api/app/` — FastAPI routes and models  
- `services/ml-inference/` — ML model serving  

**Ready for:** Issue tracking, component implementation, or full project hand-off.

---
*Saved from Ankit's handoff message, 21 Nov 2026. Note: his message said the Live Screen info text as "Put the call on speaker" (corrected here from an OCR-style typo in the paste).*
