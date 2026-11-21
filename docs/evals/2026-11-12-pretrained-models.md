# Eval — pretrained ML backends (2026-11-12)

**What this is:** a small, reproducible smoke eval of the two new
pretrained backends (ECAPA-TDNN speaker verification, AASIST
anti-spoofing), run on the day they were integrated. **What it is
not:** a benchmark. 10 bona fide + 10 synthetic clips and 45 speaker
pairs cannot establish production accuracy, and no number here may be
quoted as one. Raw per-clip/pair results are in
`2026-11-12-pretrained-results.json` (AASIST run) and
`2026-11-12-pretrained-results-wav2vec2-hemmgg.json` (earlier run of
the same script with the HF wav2vec2 checkpoint — kept because its
failure is part of the record).

- **Date:** 2026-11-12
- **Machine:** dev VM, AMD EPYC 9D25 (4 vCPU exposed, ~1.5 CPU
  throttled share), ~8 GB RAM, Linux 7.0.0-44, Python 3.12.3
- **ML venv (`.venv-ml`):** torch 2.15.0+cpu, torchaudio 2.11.1+cpu,
  speechbrain 1.1.2, transformers 5.22.2, piper-tts 1.8.0,
  onnxruntime 1.31.1, numpy 2.5.4
- **Script:** `scripts/eval_pretrained.py` —
  `PYTHONPATH=services/ml-inference:services/voiceprint .venv-ml/bin/python scripts/eval_pretrained.py --out docs/evals/2026-11-12-pretrained-results.json`
- **Runtime:** ~90 s for the full script after model downloads
  (excluding the one-time ~347 MB LibriSpeech download and checkpoint
  downloads; first ECAPA load incl. checkpoint download ≈ 57 s,
  first AASIST/wav2vec2 loads ≈ 50 s each on this network).

## Data

- **Bona fide:** LibriSpeech **test-clean**
  (https://www.openslr.org/resources/12/test-clean.tar.gz), speakers
  **1089** and **1188**, first 5 utterances each in sorted id order
  (chapters 134686 / 133604), durations 2.7–18.0 s. 10 utterances.
- **Spoof:** **locally synthesised speech — NOT a public spoof
  corpus.** Each bona fide transcript was read aloud by **Piper TTS**
  (neural TTS, voice `en_US-amy-medium`,
  https://huggingface.co/rhasspy/piper-voices). The TTS voice is
  neither LibriSpeech speaker, so this tests **TTS detection only** —
  it says nothing about voice-conversion / cloned-voice detection,
  which is the harder half of the product problem and remains
  unevaluated (PLAN.md §6.3 self-generated clone set still TODO).
- An ASVspoof/WaveFake HF sample was considered first:
  `DeepFense/WaveFake`'s parquet is 1.5 MB (metadata-scale, not a
  usable audio sample set), and `LanceaKing/asvspoof2019` ships only
  dummy data — so the documented local-synthesis route was used.

## Speaker verification — ECAPA separates, MFCC does not

All unordered pairs over the 10 utterances: 20 same-speaker pairs,
25 different-speaker pairs. Embeddings via the production code paths
(`voiceprint.ecapa` / `voiceprint.embedding`).

| Backend | Dim | Same-speaker cosine (mean, n=20) | Different-speaker cosine (mean, n=25) | Same range | Diff range |
|---|---|---|---|---|---|
| ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) | 192 | **0.7827** | **0.2367** | 0.491–0.931 | 0.116–0.326 |
| MFCC baseline (`mfcc-stats-v0`) | 44 | 0.9978 | 0.9956 | 0.993–1.000 | 0.991–0.998 |

Reading: ECAPA's same/different distributions do not overlap on this
set (worst same-speaker pair 0.491 > best different-speaker pair
0.326). The MFCC baseline is saturated near 1.0 for *every* pair of
clean read-speech clips — it carries almost no speaker information
here, exactly the weakness its module docstring warns about. This is
the measured justification for making ECAPA the production path.
Note the API's starting voiceprint threshold (0.80, tuned as a guess
for MFCC) is **not** calibrated for ECAPA; on this tiny set a
threshold anywhere in (0.33, 0.49) separates perfectly, but picking
one properly needs a real eval set (PLAN.md §6.4) — not done here.
Ad-hoc spot check during development (different chapter, 134691):
same-speaker cosine 0.6356, different-speaker 0.1408.

## Anti-spoofing — AASIST runs and points the right way; the HF wav2vec2 fine-tunes did not

Aggregate spoof score = mean of per-4 s-window scores through the
production `analyze()` path. Threshold 0.5 for accuracy; AUC is the
rank AUC of spoof scores vs bona fide scores.

| Detector | Bona fide mean (n=10) | Spoof mean (n=10) | Accuracy @0.5 | AUC |
|---|---|---|---|---|
| **AASIST (official weights, ASVspoof 2019 LA)** — new default `pretrained` | 0.1577 | 0.4003 | 0.65 | 0.71 |
| Heuristic baseline (for comparison) | 0.4267 | 0.5266 | 0.70 | 0.87 |
| HF `Hemgg/Deepfake-audio-detection` (wav2vec2-base) | 0.6656 | 0.3834 | **0.15** | **0.14** |

Per-clip AASIST scores — bona fide:
`1089-134686-0000: 0.3376, -0001: 0.0002, -0002: 0.5001, -0003: 0.0000,
-0004: 0.5000, 1188-133604-0000: 0.0007, -0001: 0.0070, -0002: 0.1824,
-0003: 0.0194, -0004: 0.0294`.
Spoof (Piper): `1089-…-0000: 0.6946, -0001: 0.0001, -0002: 0.5020,
-0003: 0.0001, -0004: 0.0183, 1188-…-0000: 0.2009, -0001: 0.4341,
-0002: 0.7227, -0003: 0.6600, -0004: 0.7697`.

Honest reading:

- AASIST's direction is right (spoof mean 2.5× the bona fide mean)
  and 8/10 bona fide clips score ≤ 0.34 — but it **misses several
  Piper clips**, especially the shortest ones (2.7–2.9 s clips score
  ≈ 0.0001; short windows are repeat-padded to AASIST's 64600-sample
  input, which may blunt it) and two bona fide clips land at exactly
  0.5. On this 20-clip set the untrained heuristic's AUC (0.87) is
  actually higher than AASIST's (0.71). Nobody should read either
  number as a ranking of the two detectors in general: n=20, one TTS
  engine, one language/register (audiobook English). What the eval
  *does* establish: AASIST loads, runs on CPU in ~1–2 s per clip,
  produces calibrated-looking, label-consistent scores through the
  production interface, and is not degenerate.
- The HF wav2vec2 route **failed this eval**: the Hemgg checkpoint
  scored bona fide audiobook speech as *more* synthetic than neural
  TTS (AUC 0.14 — strongly inverted). It stays selectable via
  `SWAR_SPOOF_MODEL` for experimentation but is not the default, and
  the heuristic remains the overall default backend
  (`SWAR_SPOOF_BACKEND` unset ⇒ heuristic).
- Other checkpoints tried and rejected on 2026-11-12 (probe clips:
  2 LibriSpeech + short/long Piper):
  - `mo-thecreator/Deepfake-audio-detection`: P(fake) = 0.0 for
    **every** probe, including 16 s of TTS — degenerate.
  - `WWWxp/wav2vec2_spoof_dection1` (ASVspoof2019 fine-tune):
    aggregate ≈ 0.48 for all 20 eval clips, both classes —
    near-constant, no discrimination.
  - `Gustking/wav2vec2-large-xlsr-deepfake-audio-classification`:
    did not finish loading within 270 s on this VM (1.2 GB XLSR-large
    checkpoint, CPU-throttled) — impractical here, not evaluated.

## Failure / environment record

- First `pip install torch torchaudio --index-url
  https://download.pytorch.org/whl/cpu` attempt failed with
  `ReadTimeoutError` against download.pytorch.org (15 s default
  timeout); retrying with `--timeout 120 --retries 10` succeeded.
  torch resolved to 2.15.0+cpu and torchaudio to 2.11.1+cpu from the
  CPU index (version skew noted; SpeechBrain's EncoderClassifier and
  torchaudio loading both worked in practice).
- The original PLAN-era blocker (SpeechBrain install failing on disk
  quota during the torch wheel download) did **not** recur: 127 GB
  disk free on this VM.
- Selecting a pretrained backend in the base venv (no torch) fails
  loudly with a `RuntimeError` pointing at `requirements-ml.txt` —
  covered by `tests/test_pretrained_backends.py`. Importing either
  package, and booting the API with a pretrained backend selected,
  never downloads or loads weights (lazy load on first use).

## What is still NOT evaluated

- Voice-clone / voice-conversion spoofing (the actual scam vector) —
  needs the consented self-generated clone set (PLAN.md §6.3).
- ASVspoof 2019/2021 EER — AASIST's authors report EER 0.83% /
  min t-DCF 0.0275 on ASVspoof 2019 LA eval with these weights; that
  is their published number, not measured here.
- ECAPA threshold calibration, Hindi/code-mixed speech, phone codecs,
  noisy/emotional speech (PLAN.md §6.3 hard negatives).
- Latency under load (single-clip timings above only).
