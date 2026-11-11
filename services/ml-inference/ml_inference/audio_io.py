"""Audio loading for SwarRaksha.

Loads common audio formats, converts to mono float32 at 16 kHz.
Primary decoder: soundfile (libsndfile). Fallback: ffmpeg CLI, used for
formats libsndfile cannot open on this platform (e.g. some WebM/Opus
browser recordings).
"""
from __future__ import annotations

import io
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

TARGET_SR = 16000


def _resample(samples: np.ndarray, sr: int) -> np.ndarray:
    if sr == TARGET_SR:
        return samples.astype(np.float32)
    # Rational resample to 16 kHz.
    from math import gcd

    g = gcd(sr, TARGET_SR)
    return resample_poly(samples, TARGET_SR // g, sr // g).astype(np.float32)


def _ffmpeg_decode(data: bytes, suffix: str) -> tuple[np.ndarray, int]:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fin:
        fin.write(data)
        fin_path = fin.name
    out_path = fin_path + ".wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", fin_path,
             "-ac", "1", "-ar", str(TARGET_SR), out_path],
            check=True, capture_output=True, timeout=60,
        )
        samples, sr = sf.read(out_path, dtype="float32", always_2d=False)
        return np.asarray(samples, dtype=np.float32), sr
    finally:
        for p in (fin_path, out_path):
            if os.path.exists(p):
                os.unlink(p)


def load_audio(data: bytes, filename: str = "audio.wav") -> tuple[np.ndarray, int]:
    """Decode raw file bytes -> (mono float32 samples @16kHz, 16000)."""
    suffix = os.path.splitext(filename or "")[1].lower() or ".wav"
    try:
        samples, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        mono = samples.mean(axis=1)
        return _resample(mono, sr), TARGET_SR
    except Exception:
        samples, sr = _ffmpeg_decode(data, suffix)
        return _resample(samples, sr), TARGET_SR


def load_audio_file(path: str) -> tuple[np.ndarray, int]:
    with open(path, "rb") as f:
        return load_audio(f.read(), os.path.basename(path))
