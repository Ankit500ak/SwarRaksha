"""Speaker embedding baseline — MFCC statistics (44-dim).

WHAT THIS IS: an untrained MFCC-statistics embedding used to wire the
enrollment/verification pipeline end-to-end (PLAN.md Section 6.2).

WHAT THIS IS NOT: a biometric-grade speaker verifier. PLAN.md specifies
ECAPA-TDNN embeddings (SpeechBrain pretrained, 192-dim). SpeechBrain was
NOT installed in this build — the install attempt failed on this VM
(disk quota while downloading the torch wheel) — so this documented
MFCC baseline ships instead. It will confuse similar voices and channel
conditions; thresholds in the API are starting values, not calibrated
operating points. See services/ml-inference/MODEL_CARD.md.

PRODUCTION TODO (PLAN.md Section 11): embeddings must be encrypted at
rest. In this local build they are stored as plain float blobs in the
local database — do not treat them as protected.
"""
from __future__ import annotations

import numpy as np
from scipy.fft import dct

EMBEDDING_DIM = 44
EMBEDDING_KIND = "mfcc-stats-v0"
N_MFCC = 20
N_MELS = 26


def _mfcc(samples: np.ndarray, sr: int) -> np.ndarray:
    """Return MFCC matrix [frames x N_MFCC]."""
    pre = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
    win = int(0.025 * sr)
    hop = int(0.010 * sr)
    n_frames = max(1 + (len(pre) - win) // hop, 0)
    if n_frames == 0:
        return np.zeros((0, N_MFCC))
    frames = np.stack([pre[i * hop: i * hop + win] for i in range(n_frames)])
    frames = frames * np.hanning(win)
    power = (np.abs(np.fft.rfft(frames, n=512)) ** 2) / 512

    def hz2mel(hz): return 2595 * np.log10(1 + hz / 700)
    def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)

    mel_pts = np.linspace(hz2mel(100), hz2mel(sr / 2), N_MELS + 2)
    hz_pts = mel2hz(mel_pts)
    bins = np.floor((512 + 1) * hz_pts / sr).astype(int)
    fb = np.zeros((N_MELS, power.shape[1]))
    for j in range(N_MELS):
        lo, ce, hi = bins[j], bins[j + 1], bins[j + 2]
        for k in range(lo, ce):
            if ce > lo:
                fb[j, k] = (k - lo) / (ce - lo)
        for k in range(ce, hi):
            if hi > ce:
                fb[j, k] = (hi - k) / (hi - ce)
    feats = np.dot(power, fb.T)
    feats = np.where(feats <= 0, np.finfo(float).eps, feats)
    log_feats = np.log(feats)
    return dct(log_feats, type=2, axis=1, norm="ortho")[:, :N_MFCC]


def _f0_stats(samples: np.ndarray, sr: int) -> tuple[float, float, float]:
    """(mean log2 F0 over voiced frames, semitone std, voiced ratio)."""
    win = int(0.025 * sr)
    hop = int(0.010 * sr)
    min_lag, max_lag = int(sr / 400), int(sr / 50)
    window = np.hanning(win)
    f0s = []
    n = max((len(samples) - win) // hop, 0)
    for i in range(n):
        frame = samples[i * hop: i * hop + win] * window
        if np.sqrt(np.mean(frame ** 2)) < 1e-4:
            continue
        corr = np.correlate(frame, frame, mode="full")[win - 1:]
        if corr[0] <= 0:
            continue
        corr /= corr[0]
        seg = corr[min_lag:max_lag]
        if len(seg) and seg.max() >= 0.3:
            f0s.append(sr / (int(np.argmax(seg)) + min_lag))
    if len(f0s) < 5:
        return 0.0, 0.0, 0.0
    f0s = np.array(f0s)
    semis = 12 * np.log2(f0s / np.median(f0s))
    return float(np.mean(np.log2(f0s))), float(np.std(semis)), float(len(f0s) / max(n, 1))


def embed(samples: np.ndarray, sr: int) -> np.ndarray:
    """Compute the L2-normalised 44-dim embedding for one audio sample."""
    mfcc = _mfcc(samples, sr)
    if mfcc.shape[0] == 0:
        raise ValueError("audio too short to embed")
    mean = mfcc.mean(axis=0)
    std = mfcc.std(axis=0)
    logf0_mean, f0_semi_std, voiced_ratio = _f0_stats(samples, sr)
    mean_log_energy = float(np.mean(20 * np.log10(np.sqrt(np.mean(samples ** 2)) + 1e-8)))
    vec = np.concatenate([mean, std, [logf0_mean, f0_semi_std, voiced_ratio,
                                      mean_log_energy / 60.0]])
    vec = vec.astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        raise ValueError("degenerate embedding")
    return vec / norm


def enroll(sample_list: list[np.ndarray], sr: int) -> np.ndarray:
    """Average the embeddings of the enrollment samples, renormalise."""
    if not sample_list:
        raise ValueError("no enrollment samples")
    embs = [embed(s, sr) for s in sample_list]
    avg = np.mean(embs, axis=0)
    return (avg / np.linalg.norm(avg)).astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)
