# Model Card — SwarRaksha detector `baseline-heuristic-v0`

## What ships today

An **untrained, rule-based heuristic scorer** (`ml_inference/detector.py`).
It exists to wire the complete product pipeline end-to-end — upload →
windows → scores → fusion → verdict — so every other layer (API, fusion,
web UI, tests) is real and exercised. It will be replaced by a trained
anti-spoofing model (AASIST-class, PLAN.md §6.1) once the datasets and
eval harness from PLAN.md §6.3–6.4 are in place.

## How it works

Audio is resampled to 16 kHz mono and split into 4 s windows. Each window
with enough voiced speech (voiced ratio ≥ 0.15) is scored from five
interpretable sub-scores, each in [0, 1], higher = more synthetic-leaning:

| Sub-score | Weight | Acoustic prior |
|---|---|---|
| `pitch_monotony` | 0.35 | TTS/VC speech usually has flatter F0 (semitone std → 0 ⇒ score → 1) |
| `low_spectral_flux` | 0.35 | Synthetic spectra evolve more smoothly frame-to-frame |
| `flat_energy` | 0.20 | Synthetic speech often has compressed loudness dynamics |
| `high_flatness` | 0.10 | Vocoder artefacts raise spectral flatness |

Window score = weighted sum. The mapping anchors (e.g. F0 std ≥ 5
semitones ⇒ sub-score 0) are **engineering priors, not fitted
parameters**; their scales were sanity-checked against the observed
feature ranges of one local TTS narration sample so the sub-scores use
their full range — that is scale-checking, not training or evaluation.
(An "over-clean HNR" sub-score was dropped during development: the
autocorrelation HNR estimate at 25 ms frames proved too noisy to use.)

## What it is NOT

- **Not trained** on ASVspoof or any other dataset.
- **Not evaluated** — no EER/AUC/accuracy figure exists for this baseline,
  and none may be quoted for it.
- **Not reliable** as a real deepfake detector. Expect both false alarms
  (e.g. a calm, monotone human speaker) and misses (expressive modern
  voice clones). The product UI therefore always communicates *risk*,
  never certainty, and the fusion layer (§5 of PLAN.md) treats this
  score as one signal among several.
- The SpeechBrain ECAPA-TDNN path planned in PLAN.md §6.2 was **not**
  installed in this build (install attempt failed on this VM — disk
  quota during the torch wheel download). Speaker verification uses the
  MFCC baseline documented in `services/voiceprint/`.

## Speaker verification baseline

`services/voiceprint` ships an MFCC-statistics embedding (mean/std of 20
MFCCs + F0/energy statistics, 44-dim, L2-normalised) with cosine
matching. Same honesty rules: untrained, uncalibrated, a plumbing
baseline — not a biometric-grade verifier. Encryption of embeddings at
rest is a production TODO (see PLAN.md §11); in this local build they
are stored as plain blobs in the local database.

## Roadmap to a real model

1. Datasets per PLAN.md §6.3 (ASVspoof, in-the-wild, self-generated
   clones with consent, hard negatives: codecs, noise, emotional speech).
2. Frozen red-team eval set; report EER/AUC per release (PLAN.md §6.4).
3. Train/fine-tune AASIST-class anti-spoofing + ECAPA-TDNN verification;
   export ONNX; keep this heuristic as a fallback and sanity signal.
