import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ("services/ml-inference", "services/voiceprint", "apps/api"):
    sys.path.insert(0, os.path.join(ROOT, p))

_tmp = tempfile.mkdtemp(prefix="swar-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SWAR_DEV_MODE"] = "1"

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402


def synth_voice_bytes(duration_s: float = 5.0, f0_base: float = 120.0,
                      vibrato: float = 2.0, seed: int = 0) -> bytes:
    """Speech-like formant signal with mild F0 movement (a 'voice' for
    pipeline tests — synthetic by construction, labelled as such)."""
    rng = np.random.default_rng(seed)
    sr = 16000
    t = np.arange(int(sr * duration_s)) / sr
    f0 = f0_base + vibrato * np.sin(2 * np.pi * 1.7 * t) + rng.normal(0, 0.6, len(t)).cumsum() * 0.002
    phase = np.cumsum(2 * np.pi * f0 / sr)
    src = sum((1.0 / h) * np.sin(h * phase) for h in range(1, 30))
    S = np.fft.rfft(src)
    fr = np.fft.rfftfreq(len(src), 1 / sr)
    shape = (np.exp(-0.5 * ((fr - 730) / 40) ** 2) * 0.9
             + np.exp(-0.5 * ((fr - 1090) / 50) ** 2) * 0.5
             + np.exp(-0.5 * ((fr - 2440) / 70) ** 2) * 0.25 + 0.15)
    # Gentle amplitude envelope with phrase-like pauses.
    env = 0.75 + 0.25 * np.sin(2 * np.pi * 0.5 * t)
    v = np.fft.irfft(S * shape, len(src)) * env
    v = (v / np.max(np.abs(v)) * 0.7).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, v, sr, format="WAV")
    return buf.getvalue()
