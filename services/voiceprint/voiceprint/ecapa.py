"""Speaker embedding — ECAPA-TDNN via SpeechBrain (pretrained, 192-dim).

WHAT THIS IS: the production speaker-verification backend planned in
PLAN.md Section 6.2. It loads the genuinely pretrained SpeechBrain
checkpoint ``speechbrain/spkrec-ecapa-voxceleb`` (ECAPA-TDNN trained on
VoxCeleb 1+2) and exposes exactly the same interface as the MFCC
baseline in ``embedding.py``: ``embed`` / ``enroll`` / ``cosine`` /
``to_bytes`` / ``from_bytes`` plus ``EMBEDDING_DIM`` / ``EMBEDDING_KIND``.

LAZY LOADING (important): importing this module imports only numpy. The
torch / SpeechBrain imports and the checkpoint download happen on the
first ``embed()`` call, so the API still boots in environments without
torch installed (e.g. the base venv). Heavy deps live in
``services/voiceprint/requirements-ml.txt`` and are installed in the
dedicated ML venv, NOT in the base API requirements.

Selection: set ``SWAR_VOICEPRINT_BACKEND=ecapa`` (see
``voiceprint/__init__.py`` / ``voiceprint/factory.py``). Default is the
MFCC baseline.

Embeddings produced by this backend (192-dim, kind
``ecapa-tdnn-voxceleb-v1``) are NOT comparable with MFCC voiceprints
(44-dim, kind ``mfcc-stats-v0``): cosine across kinds is meaningless.
The API stores ``embedding_kind`` per voiceprint; re-enroll when
switching backends.

PRODUCTION TODO (PLAN.md Section 11): embeddings must be encrypted at
rest. That is unchanged by this backend.
"""
from __future__ import annotations

import os
import threading

import numpy as np

EMBEDDING_DIM = 192
EMBEDDING_KIND = "ecapa-tdnn-voxceleb-v1"
MODEL_ID = "speechbrain/spkrec-ecapa-voxceleb"
TARGET_SR = 16000

_classifier = None
_lock = threading.Lock()


def _savedir() -> str:
    """Where SpeechBrain caches the downloaded checkpoint."""
    override = os.environ.get("SWAR_ECAPA_SAVEDIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".cache", "swarraksha",
                        "spkrec-ecapa-voxceleb")


def _load_classifier():
    """Load (once) the pretrained ECAPA-TDNN encoder. Raises a clear
    error if the heavy ML deps are not installed."""
    global _classifier
    if _classifier is not None:
        return _classifier
    with _lock:
        if _classifier is not None:
            return _classifier
        try:
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as exc:
            raise RuntimeError(
                "SWAR_VOICEPRINT_BACKEND=ecapa requires torch + speechbrain. "
                "Install services/voiceprint/requirements-ml.txt into the ML "
                "venv (.venv-ml). The base API venv intentionally does not "
                "carry torch."
            ) from exc
        _classifier = EncoderClassifier.from_hparams(
            source=MODEL_ID,
            savedir=_savedir(),
            run_opts={"device": "cpu"},
        )
        return _classifier


def _resample_to_16k(samples: np.ndarray, sr: int) -> np.ndarray:
    if sr == TARGET_SR:
        return samples.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr, TARGET_SR)
    return resample_poly(samples, TARGET_SR // g, sr // g).astype(np.float32)


def embed(samples: np.ndarray, sr: int) -> np.ndarray:
    """Compute the L2-normalised 192-dim ECAPA embedding for one sample."""
    classifier = _load_classifier()  # raises a clear error without torch
    import torch

    if samples is None or len(samples) == 0:
        raise ValueError("audio too short to embed")
    wav = _resample_to_16k(np.asarray(samples, dtype=np.float32).flatten(), sr)
    if len(wav) < int(0.25 * TARGET_SR):
        raise ValueError("audio too short to embed")
    wav_t = torch.tensor(wav, dtype=torch.float32).unsqueeze(0)  # [1, T]
    wav_lens = torch.tensor([1.0])
    with torch.no_grad():
        emb = classifier.encode_batch(wav_t, wav_lens=wav_lens)
    vec = emb.squeeze().detach().cpu().numpy().astype(np.float32).flatten()
    if vec.shape[0] != EMBEDDING_DIM:
        raise RuntimeError(
            f"unexpected ECAPA embedding dim {vec.shape[0]}, expected {EMBEDDING_DIM}")
    norm = np.linalg.norm(vec)
    if norm == 0:
        raise ValueError("degenerate embedding")
    return (vec / norm).astype(np.float32)


def enroll(sample_list: list[np.ndarray], sr: int) -> np.ndarray:
    """Average the embeddings of the enrollment samples, renormalise."""
    if not sample_list:
        raise ValueError("no enrollment samples")
    embs = [embed(s, sr) for s in sample_list]
    avg = np.mean(embs, axis=0)
    return (avg / np.linalg.norm(avg)).astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        raise ValueError(
            f"embedding shape mismatch {a.shape} vs {b.shape} — voiceprints "
            "from different backends (mfcc vs ecapa) are not comparable")
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def from_bytes(data: bytes) -> np.ndarray:
    vec = np.frombuffer(data, dtype=np.float32)
    if vec.shape[0] != EMBEDDING_DIM:
        raise ValueError(
            f"stored embedding has dim {vec.shape[0]}, ECAPA expects "
            f"{EMBEDDING_DIM} — was this voiceprint enrolled with another backend?")
    return vec
