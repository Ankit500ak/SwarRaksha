# Model Card — SwarRaksha ML backends

SwarRaksha has **two anti-spoofing backends** and **two speaker
verification backends**, selected by environment variables. The
defaults are unchanged from the baseline build; the pretrained
backends are opt-in until their eval story is stronger
(`docs/evals/2026-11-12-pretrained-models.md`).

| Signal | Backend | Selector | Model |
|---|---|---|---|
| Anti-spoofing | `heuristic` (**default**) | `SWAR_SPOOF_BACKEND=heuristic` | `baseline-heuristic-v0` — untrained, below |
| Anti-spoofing | `pretrained` | `SWAR_SPOOF_BACKEND=pretrained` | **AASIST**, official weights (ASVspoof 2019 LA); `model_version = pretrained-aasist:clovaai/aasist AASIST.pth (ASVspoof2019-LA)` |
| Speaker verification | `mfcc` (**default**) | `SWAR_VOICEPRINT_BACKEND=mfcc` | `mfcc-stats-v0` — untrained 44-dim baseline |
| Speaker verification | `ecapa` | `SWAR_VOICEPRINT_BACKEND=ecapa` | **ECAPA-TDNN**, `speechbrain/spkrec-ecapa-voxceleb`, 192-dim; `embedding_kind = ecapa-tdnn-voxceleb-v1` |

Heavy deps (torch etc.) live in `services/*/requirements-ml.txt` and
the `.venv-ml` venv — never in the base API requirements. Both
pretrained backends lazy-load: importing the packages and booting the
API never downloads weights, and selecting a pretrained backend
without its deps fails loudly at first use, never silently falls
back. `SWAR_SPOOF_MODEL` can point the anti-spoofing backend at a
HuggingFace wav2vec2 checkpoint instead of AASIST (experimental —
see the eval doc for why the tried checkpoints are not defaults).

---

## Anti-spoofing default — `baseline-heuristic-v0` (untrained)

An **untrained, rule-based heuristic scorer** (`ml_inference/detector.py`).
It exists to wire the complete product pipeline end-to-end — upload →
windows → scores → fusion → verdict — so every other layer (API, fusion,
web UI, tests) is real and exercised.

Audio is resampled to 16 kHz mono and split into 4 s windows. Each window
with enough voiced speech (voiced ratio ≥ 0.15) is scored from
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
their full range — that is scale-checking, not training.

**What it is NOT:** not trained on ASVspoof or any dataset; not
reliable as a real deepfake detector. Expect both false alarms (e.g.
a calm, monotone human speaker) and misses (expressive modern voice
clones). The product UI therefore always communicates *risk*, never
certainty, and the fusion layer (PLAN.md §5) treats this score as one
signal among several. (Its one measured number: on the 20-clip smoke
eval in `docs/evals/2026-11-12-pretrained-models.md` it scored AUC
0.87 / accuracy 0.70 — a smoke result on one TTS engine, **not** a
benchmark and not a claim.)

## Anti-spoofing pretrained — AASIST (official weights)

`ml_inference/aasist_detector.py` + vendored MIT-licensed model code
(`ml_inference/aasist_model.py`, from
https://github.com/clovaai/aasist). AASIST (Jung et al., 2022) is the
architecture PLAN.md §6.1 names: a spectro-temporal graph-attention
network over a RawNet2-style encoder, fed raw 16 kHz waveform at
exactly 64600 samples (~4 s — our window size; shorter windows are
repeat-padded, as in the authors' own data pipeline). Weights are the
authors' official `AASIST.pth`, trained on **ASVspoof 2019 LA**;
the authors report EER 0.83% / min t-DCF 0.0275 on the ASVspoof 2019
LA eval set — *their* published benchmark, not measured by us.
Class convention verified from the official source: index 0 = spoof,
index 1 = bonafide; our score is softmax P(spoof).

Measured here (20-clip smoke eval, details and per-clip scores in
the eval doc): bona fide mean 0.158, Piper-TTS mean 0.400,
accuracy@0.5 0.65, AUC 0.71. Direction is right; short TTS clips are
missed. **Not production-validated** — hence opt-in, not default.

## Speaker verification — MFCC baseline (default) vs ECAPA-TDNN

`services/voiceprint` default is still the MFCC-statistics embedding
(mean/std of 20 MFCCs + F0/energy statistics, 44-dim, L2-normalised)
with cosine matching: untrained, uncalibrated, a plumbing baseline —
not a biometric-grade verifier.

The `ecapa` backend (`voiceprint/ecapa.py`) loads SpeechBrain's
pretrained ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`, trained
on VoxCeleb 1+2) and produces 192-dim L2-normalised embeddings with
the same interface. Measured on LibriSpeech test-clean (2 speakers ×
5 utterances, eval doc): **same-speaker cosine mean 0.783 vs
different-speaker 0.237, distributions non-overlapping**, while the
MFCC baseline sat at 0.998 vs 0.996 (no separation). ECAPA is the
production-intended verifier; it stays opt-in in this change only
because (a) existing stored voiceprints are MFCC and the two kinds
are **not comparable** (re-enrollment is required when switching —
the API stores `embedding_kind` per voiceprint and the ECAPA module
raises on dimension mismatch), and (b) the cosine threshold is not
yet calibrated for ECAPA.

Encryption of embeddings at rest is a production TODO (PLAN.md §11)
for both backends; in this local build they are stored as plain blobs
in the local database.

## Roadmap

1. Datasets per PLAN.md §6.3 (ASVspoof, in-the-wild, self-generated
   clones with consent, hard negatives: codecs, noise, emotional speech).
2. Frozen red-team eval set; report EER/AUC per release (PLAN.md §6.4);
   calibrate the ECAPA threshold and the fusion thresholds on it,
   then flip the pretrained backends to default.
3. ONNX export for the pretrained models; keep the heuristic as a
   fallback and sanity signal.
