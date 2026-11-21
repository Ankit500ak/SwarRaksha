"""Pretrained anti-spoofing detector — dispatcher (AASIST default).

WHAT THIS IS: genuinely pretrained models behind the same interface
as the heuristic baseline in ``detector.py``, selected by
``SWAR_SPOOF_MODEL``:

- ``aasist`` (DEFAULT): AASIST with the authors' official pretrained
  weights (ASVspoof 2019 LA) — see ``aasist_detector.py``. This is the
  architecture PLAN.md Section 6.1 names, it is tiny (1.3 MB weights),
  fast on CPU, and it was the best-behaved checkpoint on our local
  eval (``docs/evals/2026-11-12-pretrained-models.md``).
- any HuggingFace model id: a wav2vec2 audio-classification fine-tune
  loaded via ``transformers``. The spoof score is the softmax
  probability of the checkpoint's *fake* class, resolved from its own
  ``config.id2label`` (loading fails loudly if no fake-like label
  exists). Example: ``SWAR_SPOOF_MODEL=Hemgg/Deepfake-audio-detection``.

Checkpoint selection was verified by actually running candidates on
2026-11-12 (full record in the eval doc):
- ``mo-thecreator/Deepfake-audio-detection`` — REJECTED: P(fake)=0.0
  for every probe clip including 16 s of neural TTS (degenerate
  always-"real" output on this data).
- ``WWWxp/wav2vec2_spoof_dection1`` (ASVspoof2019 fine-tune) —
  REJECTED: near-constant ~0.48 aggregate for bona fide and spoof
  clips alike (no discrimination on this data).
- ``Gustking/wav2vec2-large-xlsr-deepfake-audio-classification`` —
  REJECTED for this machine: the 1.2 GB XLSR-large checkpoint did not
  finish loading within 270 s on the CPU-throttled dev VM.
- ``Hemgg/Deepfake-audio-detection`` — loads and runs, but on our
  eval it scored bona fide LibriSpeech as MORE synthetic than Piper
  TTS (AUC 0.14): kept available via ``SWAR_SPOOF_MODEL``, NOT the
  default, and its eval failure is documented, not hidden.

LAZY LOADING: importing this module imports only numpy/scipy. torch /
transformers imports and any checkpoint download happen on the first
scored window, so the API boots without the heavy deps. Install them
from ``services/ml-inference/requirements-ml.txt`` into the ML venv.

``MODEL_VERSION`` names the exact checkpoint that will score, so
every stored check is traceable to the model that produced it.
"""
from __future__ import annotations

import os
import threading

import numpy as np

DEFAULT_MODEL_ID = "aasist"
MODEL_ID = os.environ.get("SWAR_SPOOF_MODEL", DEFAULT_MODEL_ID)
TARGET_SR = 16000
# wav2vec2 fine-tunes are typically trained on clips of a few seconds;
# cap a single forward pass at 10 s and centre-crop longer windows.
MAX_FORWARD_SEC = 10.0

_FAKE_LABEL_HINTS = ("fake", "spoof", "synthetic", "deepfake", "aivoice", "ai_voice", "generated")
_REAL_LABEL_HINTS = ("real", "human", "bonafide", "bona_fide", "genuine")

_model = None
_extractor = None
_fake_idx: int | None = None
_lock = threading.Lock()


def _is_aasist() -> bool:
    return MODEL_ID.strip().lower() == "aasist"


def _model_version() -> str:
    if _is_aasist():
        from .aasist_detector import MODEL_VERSION as aasist_version

        return aasist_version
    return f"pretrained-wav2vec2:{MODEL_ID}"


MODEL_VERSION = _model_version()


def _resolve_fake_index(id2label: dict) -> int:
    labels = {int(k): str(v).strip().lower() for k, v in id2label.items()}
    fake = [i for i, lab in labels.items()
            if any(h in lab.replace(" ", "_") for h in _FAKE_LABEL_HINTS)]
    real = [i for i, lab in labels.items()
            if any(h in lab.replace(" ", "_") for h in _REAL_LABEL_HINTS)]
    if len(fake) != 1 or not real:
        raise RuntimeError(
            f"cannot resolve fake/real classes from checkpoint labels {labels}; "
            "refusing to guess which output is the spoof probability")
    return fake[0]


def _load_hf():
    """Load (once) the HF checkpoint. Raises a clear error if the
    heavy ML deps are not installed."""
    global _model, _extractor, _fake_idx
    if _model is not None:
        return _model, _extractor, _fake_idx
    with _lock:
        if _model is not None:
            return _model, _extractor, _fake_idx
        try:
            from transformers import (AutoFeatureExtractor,
                                      AutoModelForAudioClassification)
        except ImportError as exc:
            raise RuntimeError(
                "SWAR_SPOOF_BACKEND=pretrained requires torch + transformers. "
                "Install services/ml-inference/requirements-ml.txt into the "
                "ML venv (.venv-ml). The base API venv intentionally does "
                "not carry torch."
            ) from exc
        extractor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
        model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)
        model.eval()
        _fake_idx = _resolve_fake_index(model.config.id2label)
        _extractor, _model = extractor, model
        return _model, _extractor, _fake_idx


def _resample_to_16k(samples: np.ndarray, sr: int) -> np.ndarray:
    if sr == TARGET_SR:
        return samples.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr, TARGET_SR)
    return resample_poly(samples, TARGET_SR // g, sr // g).astype(np.float32)


def score_window(samples: np.ndarray, sr: int) -> dict:
    """Score one window with the selected pretrained checkpoint.

    Same return shape as the heuristic ``detector.score_window``.
    Windows shorter than 0.5 s return ``spoof_score=None`` (too little
    signal, mirroring the baseline's insufficient-speech behaviour).
    """
    if _is_aasist():
        from .aasist_detector import score_window as _aasist_score

        return _aasist_score(samples, sr)
    wav = _resample_to_16k(np.asarray(samples, dtype=np.float32).flatten(), sr)
    if len(wav) < int(0.5 * TARGET_SR):
        return {"spoof_score": None, "sufficient_speech": False,
                "features": {}, "subscores": None}
    max_len = int(MAX_FORWARD_SEC * TARGET_SR)
    if len(wav) > max_len:  # centre-crop
        start = (len(wav) - max_len) // 2
        wav = wav[start:start + max_len]
    model, extractor, fake_idx = _load_hf()  # clear error without torch
    import torch

    inputs = extractor(wav, sampling_rate=TARGET_SR, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0].detach().cpu().numpy()
    score = float(probs[fake_idx])
    return {
        "spoof_score": round(min(1.0, max(0.0, score)), 4),
        "sufficient_speech": True,
        "features": {"pretrained_fake_prob": round(score, 4)},
        "subscores": None,
    }
