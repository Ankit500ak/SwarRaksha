"""Pretrained anti-spoofing detector — AASIST (official weights).

WHAT THIS IS: the AASIST model from PLAN.md Section 6.1, using the
authors' official implementation (vendored MIT-licensed code in
``aasist_model.py``, Jung et al., NAVER Corp / clovaai) and their
official pretrained weights ``AASIST.pth`` (trained on ASVspoof 2019
LA; reported by the authors at EER 0.83% on the ASVspoof 2019 LA eval
set — that is THEIR benchmark number on THEIR data, not a SwarRaksha
measurement; our own small local eval is in
``docs/evals/2026-11-12-pretrained-models.md``).

Input convention (from the official config ``config/AASIST.conf``):
raw waveform at 16 kHz, exactly ``nb_samp=64600`` samples (~4.04 s) —
windows are truncated/repeat-padded to that length exactly as the
authors' own ``pad()`` in ``data_utils.py`` does. Output convention
(verified in the official ``main.py``/``data_utils.py``): class index
1 = bonafide, index 0 = spoof. The spoof score here is the softmax
probability of class 0.

LAZY LOADING: importing this module imports only numpy/scipy. The
weights (~1.3 MB) are downloaded from the official GitHub repo on
first use into ``~/.cache/swarraksha/aasist/`` (override with
``SWAR_AASIST_WEIGHTS`` / ``SWAR_AASIST_CACHE``), and torch is imported
only then, so the API boots without the heavy deps.
"""
from __future__ import annotations

import os
import threading
import urllib.request

import numpy as np

MODEL_VERSION = "pretrained-aasist:clovaai/aasist AASIST.pth (ASVspoof2019-LA)"
WEIGHTS_URL = ("https://raw.githubusercontent.com/clovaai/aasist/main/"
               "models/weights/AASIST.pth")
TARGET_SR = 16000
NB_SAMP = 64600  # official model_config.nb_samp

# Official model_config from config/AASIST.conf (architecture AASIST).
_MODEL_CONFIG = {
    "architecture": "AASIST",
    "nb_samp": NB_SAMP,
    "first_conv": 128,
    "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
    "gat_dims": [64, 32],
    "pool_ratios": [0.5, 0.7, 0.5, 0.5],
    "temperatures": [2.0, 2.0, 100.0, 100.0],
}

_model = None
_lock = threading.Lock()


def _weights_path() -> str:
    override = os.environ.get("SWAR_AASIST_WEIGHTS")
    if override:
        return override
    cache = os.environ.get(
        "SWAR_AASIST_CACHE",
        os.path.join(os.path.expanduser("~"), ".cache", "swarraksha", "aasist"))
    return os.path.join(cache, "AASIST.pth")


def _load():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "SWAR_SPOOF_BACKEND=pretrained (AASIST) requires torch. "
                "Install services/ml-inference/requirements-ml.txt into "
                "the ML venv (.venv-ml). The base API venv intentionally "
                "does not carry torch."
            ) from exc
        path = _weights_path()
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            urllib.request.urlretrieve(WEIGHTS_URL, tmp)
            os.replace(tmp, path)
        from .aasist_model import Model

        model = Model(_MODEL_CONFIG)
        state = torch.load(path, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model.eval()
        _model = model
        return _model


def _pad_or_truncate(wav: np.ndarray) -> np.ndarray:
    """Match the authors' data_utils.pad(): truncate to NB_SAMP, or
    repeat-tile a shorter clip up to NB_SAMP."""
    if len(wav) >= NB_SAMP:
        return wav[:NB_SAMP]
    repeats = int(np.ceil(NB_SAMP / max(len(wav), 1)))
    return np.tile(wav, repeats)[:NB_SAMP]


def _resample_to_16k(samples: np.ndarray, sr: int) -> np.ndarray:
    if sr == TARGET_SR:
        return samples.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr, TARGET_SR)
    return resample_poly(samples, TARGET_SR // g, sr // g).astype(np.float32)


def score_window(samples: np.ndarray, sr: int) -> dict:
    """Score one window with AASIST. Same shape as the heuristic
    ``detector.score_window``. Windows < 0.5 s return None."""
    wav = _resample_to_16k(np.asarray(samples, dtype=np.float32).flatten(), sr)
    if len(wav) < int(0.5 * TARGET_SR):
        return {"spoof_score": None, "sufficient_speech": False,
                "features": {}, "subscores": None}
    model = _load()  # raises a clear error without torch
    import torch
    x = torch.tensor(_pad_or_truncate(wav), dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        _, logits = model(x)
    probs = torch.softmax(logits, dim=-1)[0].detach().cpu().numpy()
    score = float(probs[0])  # class 0 = spoof (official label convention)
    return {
        "spoof_score": round(min(1.0, max(0.0, score)), 4),
        "sufficient_speech": True,
        "features": {"pretrained_fake_prob": round(score, 4)},
        "subscores": None,
    }
