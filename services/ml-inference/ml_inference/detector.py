"""SwarRaksha baseline anti-spoofing detector (v0 heuristic).

WHAT THIS IS: an UNTRAINED, rule-based scorer over interpretable acoustic
features (pitch monotony, spectral flux, energy dynamics, spectral
flatness, harmonic-to-noise ratio). It exists to wire the full product
pipeline end-to-end and to be replaced by a trained model (AASIST-class,
PLAN.md Section 6.1) once the eval harness and datasets land.

WHAT THIS IS NOT: a validated deepfake detector. No benchmark accuracy
is claimed anywhere. See MODEL_CARD.md.
"""
from __future__ import annotations

import numpy as np

from .features import window_features

WINDOW_SEC = 4.0
MODEL_VERSION = "baseline-heuristic-v0"

# Sub-score weights (documented in MODEL_CARD.md).
WEIGHTS = {
    "pitch_monotony": 0.35,
    "low_spectral_flux": 0.35,
    "flat_energy": 0.20,
    "high_flatness": 0.10,
}


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _subscores(f: dict) -> dict:
    """Map raw features to synthetic-leaning sub-scores in [0, 1].

    Mapping anchors are engineering priors from the anti-spoofing
    literature (TTS/VC speech tends to be prosodically flatter and
    spectrally smoother than spontaneous human speech). They are NOT
    fitted to data — calibration is future work (PLAN.md Section 6.4).
    """
    # F0 spread (after octave folding): 1 semitone std -> 1.0 (monotone),
    # >= 5 semitones -> 0.0 (expressive prosody).
    pitch = _clamp01((5.0 - f["f0_semi_std"]) / 4.0)
    # Normalised spectral flux: 0.25 -> 1.0 (near-static spectrum),
    # >= 0.75 -> 0.0.
    flux = _clamp01((0.75 - f["spectral_flux"]) / 0.50)
    # Voiced-frame energy dynamics: 1 dB std -> 1.0, >= 7 dB -> 0.0.
    energy = _clamp01((7.0 - f["energy_std_db"]) / 6.0)
    # Spectral flatness (speech band): 0.05 -> 0.0, >= 0.35 -> 1.0.
    flatness = _clamp01((f["spectral_flatness"] - 0.05) / 0.30)
    return {
        "pitch_monotony": pitch,
        "low_spectral_flux": flux,
        "flat_energy": energy,
        "high_flatness": flatness,
    }


def score_window(samples: np.ndarray, sr: int) -> dict:
    """Score one window. Windows with little voiced speech return
    score=None so fusion can ignore them instead of guessing."""
    f = window_features(samples, sr)
    if f["voiced_ratio"] < 0.15:
        return {
            "spoof_score": None,
            "sufficient_speech": False,
            "features": f,
            "subscores": None,
        }
    subs = _subscores(f)
    score = sum(WEIGHTS[k] * subs[k] for k in WEIGHTS)
    return {
        "spoof_score": round(_clamp01(score), 4),
        "sufficient_speech": True,
        "features": {k: round(v, 4) for k, v in f.items()},
        "subscores": {k: round(v, 4) for k, v in subs.items()},
    }


def analyze(samples: np.ndarray, sr: int) -> dict:
    """Split audio into 4 s windows, score each, aggregate."""
    win = int(WINDOW_SEC * sr)
    windows = []
    if len(samples) == 0:
        return {"model_version": MODEL_VERSION, "windows": [],
                "aggregate_spoof": None, "speech_windows": 0}
    for i, start in enumerate(range(0, len(samples), win)):
        chunk = samples[start:start + win]
        if len(chunk) < sr // 2:  # ignore trailing fragments < 0.5 s
            continue
        res = score_window(chunk, sr)
        res_out = {
            "index": i,
            "t_start": round(start / sr, 2),
            "t_end": round((start + len(chunk)) / sr, 2),
            **res,
        }
        windows.append(res_out)
    scored = [w["spoof_score"] for w in windows if w["spoof_score"] is not None]
    aggregate = round(float(np.mean(scored)), 4) if scored else None
    return {
        "model_version": MODEL_VERSION,
        "windows": windows,
        "aggregate_spoof": aggregate,
        "speech_windows": len(scored),
    }
