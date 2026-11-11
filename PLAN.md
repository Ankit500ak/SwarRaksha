# SwarRaksha — Complete Production Plan

**Product:** SwarRaksha — real-time AI shield against voice-clone scam calls
**Tagline:** Every voice, verified.
**Owner:** Ankit Pal
**Status:** Planning v1.0 · 11 Nov 2026
**Repo:** github.com/Ankit500ak/SwarRaksha

---

## 1. The problem

AI voice cloning needs only 3–10 seconds of someone's audio — a reel, a voice note, a YouTube clip — to produce a near-perfect copy of their voice. Scammers use it for "family emergency" calls: a parent hears their own child's voice crying for help and is told to transfer money immediately. Banks and police reports across India (and the FBI in the US) are flagging this as one of the fastest-growing fraud categories.

Humans cannot reliably hear the difference. Models can — synthetic speech carries artefacts (phase inconsistencies, unnatural spectral patterns, vocoder fingerprints) that anti-spoofing models are specifically trained to detect.

**SwarRaksha's job: hear what the human ear can't, and say so in time.**

## 2. Who it is for

| Persona | Situation | What SwarRaksha gives them |
|---|---|---|
| **The parent (primary)** | Receives a panic call from "their child" | A clear, calm, big-text verdict: verified / unverified / likely cloned — in Hindi or English |
| **The young professional** | Enrolls their own voiceprint, protects family | A dashboard: family members protected, alerts, scam-attempt history |
| **The cautious user** | Gets a suspicious voice note or clip | "Check this audio" — upload/paste, get a verdict in seconds |
| **(v2) Banks / call centres** | Verify customers on support calls | An API that scores voice authenticity during the call |

Design rule: the person under stress is a frightened parent, not an engineer. Every screen must be understandable in 3 seconds, in their language, with zero jargon.

## 3. What the product does — the four verbs

1. **Detect** — a streaming anti-spoofing model analyses the caller's audio in short windows (2–4 s) and outputs a "synthetic probability" per window.
2. **Verify** — the caller's voice embedding is compared against enrolled voiceprints of trusted contacts (e.g., "this claims to be your son — does it match your son?").
3. **Challenge** — when risk crosses a threshold, trigger an active check:
   - **Liveness prompt:** ask the caller to say a random phrase shown on screen (clones replaying scripts fail; real-time cloners struggle with arbitrary phrases + timing).
   - **Family code word:** prompt the user to ask for the pre-agreed family secret word — the oldest, strongest defence, built into the flow.
4. **Verdict** — one fused risk score → one screen:
   - 🟢 **Verified** — human voice + voiceprint match.
   - 🟡 **Unverified — be careful** — human-sounding but not a known voice, or signals conflict. Advice: hang up, call them back on their real number.
   - 🔴 **Likely cloned** — synthetic artefacts detected. Advice: do not send money; end the call; one-tap report.

## 4. Scope

### 4.1 MVP (v0.1) — "prove it works", ~4 weeks
- Web app (mobile-first) — no app-store dependency.
- **Check a clip:** upload/record up to 60 s of audio → verdict + per-window scores + plain-language explanation.
- **Voiceprint enrollment:** a user enrolls their own voice (3 short recordings) and up to 3 family members (with their consent flow).
- **Simulated live mode:** microphone stream analysed in near-real-time with the live risk meter (this is the demo centrepiece; true in-call interception on phones is restricted by Android/iOS and is NOT promised in MVP).
- Accounts, login (email + OTP), Hindi + English UI.
- Admin/eval dashboard (internal): model metrics, recent checks, false-alarm log.

### 4.2 v1.0 — production release
- Hardened streaming inference (ONNX, < 300 ms per window), WebSocket protocol with reconnect/resume.
- Challenge-response liveness inside live mode.
- Family circles: one admin invites members; parents get the simplest possible view.
- Alerts: if a 🔴 verdict fires on a protected member's "voice", notify the family admin.
- Observability, rate limits, abuse protection, backups, privacy policy + consent records (DPDP-aligned).
- Public landing page + the demo video.

### 4.3 v2 — after traction
- Android app with CallScreeningService exploration (within platform rules).
- B2B API for banks/call centres (per-minute pricing).
- More languages (Tamil, Telugu, Bengali, Marathi), on-device tiny model for offline clip checks.
- Continuous model improvement loop from (consented, anonymised) reported scams.

### 4.4 Explicitly out of scope
- Recording or storing calls by default. **We store embeddings and scores, not audio.**
- Identifying unknown people. SwarRaksha only verifies against voices the family enrolled with consent.
- Any claim of 100% accuracy. The product communicates risk, never certainty.

## 5. System architecture

```
┌──────────────────────── CLIENT ────────────────────────┐
│  Web app (React + TS)                                   │
│  • Record / upload audio  • Live risk meter             │
│  • Enrollment wizard      • Family dashboard            │
└──────────────┬──────────────────────┬──────────────────┘
        HTTPS (REST)           WSS (audio chunks)
┌──────────────▼──────────────────────▼──────────────────┐
│  API SERVICE (FastAPI)                                  │
│  • Auth (email OTP / JWT)  • Users & family circles     │
│  • Checks, verdicts, alerts • Rate limiting             │
└──────┬───────────────┬────────────────┬────────────────┘
       │               │                │
┌──────▼───────┐ ┌─────▼──────────┐ ┌───▼────────────────┐
│ ML INFERENCE │ │ VOICEPRINT     │ │ DATA               │
│ (Python svc) │ │ SERVICE        │ │ PostgreSQL: users, │
│ • Anti-spoof │ │ • ECAPA-TDNN   │ │ circles, checks,   │
│   (ONNX)     │ │   embeddings   │ │ voiceprints        │
│ • per-window │ │ • cosine match │ │ Redis: sessions,   │
│   scores     │ │ • thresholds   │ │ stream state       │
└──────────────┘ └────────────────┘ │ Object storage:    │
                                    │ consented samples  │
                                    │ only (encrypted)   │
                                    └────────────────────┘
```

**Why services are split:** the ML inference service scales and deploys independently of the API (model updates must not redeploy the product), and voiceprints are isolated so their access can be audited separately.

**Audio pipeline:** client captures 16 kHz mono WAV/Opus → chunks of 2–4 s over WebSocket → inference returns per-window synthetic-probability → fusion layer combines (a) spoof score trend, (b) voiceprint similarity, (c) challenge result → verdict state machine → UI.

**Fusion rule (initial, to be tuned on eval data):**
- 🔴 if spoof score > 0.8 sustained over 2+ windows, regardless of voiceprint.
- 🟢 requires spoof < 0.3 **and** voiceprint similarity above threshold.
- Everything else → 🟡. When in doubt, the product says "be careful", never "safe".

## 6. The ML plan (the heart of the project)

### 6.1 Model 1 — Anti-spoofing (is it synthetic?)
- **Architecture:** AASIST-class model (spectro-temporal graph attention) or RawNet2-class end-to-end model on raw waveform. Start from a pretrained checkpoint; fine-tune, don't train from scratch.
- **Output:** probability that the window is synthetic (TTS / voice-conversion / replay).
- **Serving:** exported to ONNX, quantised; target < 300 ms per 4 s window on a small CPU instance.

### 6.2 Model 2 — Speaker verification (is it really them?)
- **Architecture:** ECAPA-TDNN embeddings (SpeechBrain pretrained) — 192-dim voiceprint.
- **Enrollment:** 3 samples × ~10 s → averaged embedding, stored encrypted.
- **Matching:** cosine similarity vs. claimed identity; threshold tuned on eval set (start ~0.75, then calibrate).

### 6.3 Data strategy
| Source | Use | Notes |
|---|---|---|
| **ASVspoof 2019 / 2021** | Core training/eval for anti-spoofing | The standard benchmark; report EER on it |
| **"In-the-Wild" deepfake audio** | Real-world robustness eval | Real clones of public figures, ethically published for research |
| **Self-generated clones** | The key differentiator | Clone 10–15 consenting voices (own + friends/family with written consent) using current open tools (e.g., open-source TTS / voice-conversion). This tests the model against *today's* cloners, not 2019's. |
| **Indian-language speech** | Coverage | Hindi/English code-mixed samples; public corpora (e.g., Mozilla Common Voice Hindi) for bonafide speech |
| **Hard negatives** | Reduce false alarms | Phone-codec audio (8 kHz, compressed), noisy rooms, elderly voices, emotional/crying speech — a crying real son must NOT be flagged as a clone |

**Rule:** no person's voice is cloned or enrolled without explicit consent, recorded in the repo's `docs/consent/` process (template only — signed forms live outside git).

### 6.4 Evaluation — measured, never vibes
- **Anti-spoofing:** EER and AUC on ASVspoof eval + our self-generated clone set, reported separately per cloner tool. Target: EER < 8% on the self-generated set for MVP; < 5% for v1.0.
- **Verification:** false-accept vs false-reject curve; target FAR < 2% at the chosen threshold.
- **End-to-end:** a frozen "red-team set" of 50 scripted scam calls + 50 genuine calls; the verdict accuracy on this set is the number we quote publicly.
- **Latency:** p95 window-score latency < 300 ms (server) measured in load tests.
- Every model change ships only if the red-team set does not regress. Metrics live in `docs/evals/` per release.

### 6.5 Model lifecycle
- Versioned artefacts (`models/registry`), ONNX export script, canary deploy of new models to 10% of checks, automatic rollback on error-rate or latency regression.

## 7. API design (v1)

Base: `https://api.swarraksha.app/v1` · Auth: Bearer JWT (email-OTP login) · All errors: `{code, message}` with i18n message keys.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/request-otp` · `/auth/verify-otp` | Login |
| POST | `/voiceprints` | Enroll a voiceprint (multipart audio ×3) |
| GET / DELETE | `/voiceprints` · `/voiceprints/{id}` | List / remove (deletion wipes embedding + samples) |
| POST | `/circles` · `/circles/{id}/invite` | Family circles |
| POST | `/checks/clip` | Upload a clip → check id |
| GET | `/checks/{id}` | Verdict, window scores, explanation |
| WSS | `/checks/live` | Streaming live check (audio chunks in, scores out) |
| POST | `/checks/{id}/challenge` | Issue/verify liveness challenge |
| POST | `/reports` | Report a scam attempt (feeds alerts + optional research set) |
| GET | `/me/alerts` | Family alerts |

## 8. Database (core tables)

`users` (id, email, name, language, created_at) · `circles` (id, owner_id, name) · `circle_members` (circle_id, user_id, role) · `voiceprints` (id, user_id, label, embedding_encrypted, sample_count, consent_at) · `checks` (id, user_id, type[clip|live], verdict, risk_score, model_version, created_at) · `check_windows` (check_id, t_start, spoof_score, spk_similarity) · `challenges` (check_id, type, result) · `reports` (id, user_id, details, created_at) · `audit_log` (actor, action, target, at).

## 9. Frontend — screens

1. **Landing** — the problem in one story, live demo button, trust/privacy section.
2. **Home** — two big actions: "Check a recording" / "Start live check"; family protection status.
3. **Check flow** — record/upload → analysing animation → verdict screen (colour + plain-language why + what to do next).
4. **Live mode** — risk meter, rolling verdict, "Ask for code word" button, end & save summary.
5. **Enroll voice** — guided 3-sample wizard with quality feedback (too noisy / too short).
6. **Family** — members, who's protected, alert history.
7. **Settings** — language (EN/HI), data controls: download my data, delete my voiceprint, delete account.

Accessibility: large type mode by default for the verdict screens; full Hindi localisation at v1.0, not "later".

## 10. Infrastructure & DevOps

- **Containers:** one Dockerfile per service; `docker-compose.yml` runs the whole stack locally (API + ML + Postgres + Redis).
- **CI (GitHub Actions):** lint + type-check + unit tests on every PR; model-eval smoke test on model PRs; build & push images on merge to `main`.
- **CD:** staging auto-deploys from `main`; production is a manual promote of the same image.
- **Hosting (start lean):** API + ML on a single small VPS or Render/Fly; web on Vercel; Postgres managed. Estimated starting cost: ₹0–1,500/month on free/starter tiers.
- **Observability:** structured logs (no audio, no embeddings in logs), health endpoints, uptime + latency dashboards, error tracking (Sentry free tier).
- **Backups:** daily DB backup, 7-day retention; voiceprint embeddings included (encrypted at rest).

## 11. Security & privacy (non-negotiables)

- Voiceprints stored as **encrypted embeddings**; raw enrollment audio deleted after embedding unless the user explicitly opts into research donation.
- TLS everywhere; JWT short-lived + refresh rotation; OTP rate-limited; per-user rate limits on checks (anti-abuse: the tool must not become a free "test my clone" service for scammers — clip checks are length-capped and logged).
- Consent is a product feature: enrollment requires the voice owner's own OTP-verified session.
- DPDP Act alignment: purpose limitation, data-minimisation, erasure on request, breach-notification plan in `docs/privacy/`.
- Threat model reviewed before v1.0: attacker goals include testing clones against us (mitigate: no per-window raw scores exposed publicly beyond a capped resolution, anomaly detection on repeated checks), stealing voiceprints (mitigate: encryption, isolation, audit), and social-engineering support (no manual overrides).

## 12. Testing strategy

- **Unit:** fusion/verdict logic, API contracts, embedding matching (pytest; vitest for web).
- **ML regression:** frozen eval sets run in CI for model changes (Section 6.4).
- **Integration:** full check flow against recorded scam/genuine fixtures.
- **Load:** 50 concurrent live streams before v1.0.
- **UAT script:** 5 family-scenario walkthroughs (including "crying caller") executed manually per release.

## 13. Milestones

### Phase 0 — Foundations (Days 1–3)
Repo, CI, docker-compose stack up; data downloads (ASVspoof); pretrained anti-spoof + SpeechBrain baselines running in notebooks. **Exit:** notebook demo scores one real and one cloned clip correctly.

### Phase 1 — Clip check end-to-end (Week 1–2)
FastAPI + inference service (ONNX), upload/record UI, verdict screen, eval harness v1 with the self-generated clone set (≥ 5 voices × 2 cloners). **Exit:** a stranger can open the site, upload a clip, and get a correct, explained verdict.

### Phase 2 — Voiceprints & family (Week 3)
Enrollment wizard, verification in the check flow, circles + invites, Hindi UI. **Exit:** "This claims to be your son" flow works for an enrolled family.

### Phase 3 — Live mode & challenges (Week 4)
WebSocket streaming, live risk meter, liveness prompts + code-word flow, alerts. **Exit:** the full demo scenario (Section 14) runs end-to-end. → **MVP ships.**

### Phase 4 — Production hardening (Weeks 5–6)
Load tests, security review, privacy docs, observability, canary model deploys, landing page + demo video, beta with 5 real families, fix what breaks. → **v1.0.**

### Phase 5 — v2 exploration (post-launch)
Android feasibility, B2B API pilot, more languages, on-device tiny model.

## 14. The demo (how this wins interviews)

1. Play a 10-second reel of my own voice.
2. Clone it live with an open-source tool; the clone calls in: *"Beta, I'm in trouble…"* — wait, the clone IS the "son".
3. SwarRaksha live mode runs: meter climbs, 🔴 **Likely cloned** — spoof artefacts + voiceprint mismatch.
4. Then I speak myself: 🟢 **Verified**.
5. Close: "My mother can't tell the difference. SwarRaksha can."

Record as a 2-minute video for the repo README and LinkedIn.

## 15. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Cloners improve; model decays | Self-generated clone set refreshed monthly; canary model updates; market the trend honestly |
| False 🔴 on a genuine emotional call | Hard-negative training (crying, noise, codecs); 🟡 "call them back" advice instead of panic; never block, only warn |
| Scammers abuse it to test clones | Rate limits, capped score detail, anomaly detection, no batch API in consumer tier |
| Phone OS blocks true in-call audio | MVP is mic/clip based and says so plainly; Android screening APIs explored in v2 |
| Privacy backlash | Embeddings-only, consent-first, delete-anything-anytime, DPDP-aligned docs |
| Cost of GPU inference | CPU-optimised ONNX models; the models are small by design |

## 16. Success metrics

- Red-team set verdict accuracy ≥ 90% (MVP), ≥ 95% (v1.0).
- Clip-check verdict in < 5 s for a 60 s clip; live window latency p95 < 300 ms.
- Beta: 5 families enrolled; zero unresolved false-🔴 complaints.
- Portfolio: deployed link live, demo video published, eval report in repo.

## 17. Working conventions (how we build)

- Feature branches off `main`; Conventional Commits; PRs with the eval report attached for ML changes; merge commits preserved (no squash).
- Small, real commits — the history should read like the product was actually built, because it was.
- Every "done" claim carries evidence: a test run, a metric, or a recording.

## 18. Decisions needed from Ankit

1. Repo is public from day one (portfolio value) — code only; never data, audio, or keys.
2. First cloner tools for the self-generated set (pick 2 open-source tools).
3. Beta families: 3–5 real families willing to enroll and give feedback.
4. Name lock: **SwarRaksha** · tagline "Every voice, verified." · repo `Ankit500ak/SwarRaksha`.
