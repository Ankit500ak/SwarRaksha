"""Frame-level acoustic features used by the baseline detector.

All features are computed with numpy/scipy only, restricted to the
speech band (100–4000 Hz) where relevant, and dynamics are measured on
voiced frames so pauses don't dominate. See MODEL_CARD.md for exactly
what the baseline is and is not.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import stft

FRAME_WIN = 0.025   # 25 ms
FRAME_HOP = 0.010   # 10 ms
BAND_LO, BAND_HI = 100.0, 4000.0


def _spectrogram(samples: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nperseg = int(FRAME_WIN * sr)
    noverlap = nperseg - int(FRAME_HOP * sr)
    freqs, _, zxx = stft(samples, fs=sr, window="hann", nperseg=nperseg,
                         noverlap=noverlap, boundary=None, padded=False)
    return freqs, np.abs(zxx) + 1e-10, zxx


def _frame_rms(samples: np.ndarray, sr: int, n_frames: int) -> np.ndarray:
    hop = int(FRAME_HOP * sr)
    win = int(FRAME_WIN * sr)
    return np.array([
        np.sqrt(np.mean(samples[i * hop: i * hop + win] ** 2) + 1e-12)
        for i in range(n_frames)
    ])


def _f0_track(samples: np.ndarray, sr: int) -> np.ndarray:
    """Autocorrelation F0 per frame (Hz), 0 = unvoiced.

    Octave errors are folded toward the track median and the result is
    median-smoothed, so semitone spread reflects prosody, not tracker
    noise.
    """
    win = int(FRAME_WIN * sr)
    hop = int(FRAME_HOP * sr)
    min_lag = int(sr / 400)
    max_lag = int(sr / 50)
    n = max((len(samples) - win) // hop, 0)
    window = np.hanning(win)
    f0 = np.zeros(n)
    for i in range(n):
        frame = samples[i * hop: i * hop + win] * window
        if np.sqrt(np.mean(frame ** 2)) < 1e-4:
            continue
        corr = np.correlate(frame, frame, mode="full")[win - 1:]
        if corr[0] <= 0:
            continue
        corr = corr / corr[0]
        seg = corr[min_lag:max_lag]
        if len(seg) == 0:
            continue
        lag = int(np.argmax(seg)) + min_lag
        if seg.max() >= 0.3:
            f0[i] = sr / lag
    voiced = f0 > 0
    if voiced.sum() >= 5:
        med = np.median(f0[voiced])
        folded = f0.copy()
        for i in np.where(voiced)[0]:
            while folded[i] > med * 1.6:
                folded[i] /= 2
            while folded[i] < med / 1.6:
                folded[i] *= 2
        f0 = folded
        # Median smooth (width 5) over the voiced track in-place order.
        idx = np.where(f0 > 0)[0]
        vals = f0[idx]
        sm = np.array([np.median(vals[max(0, j - 2): j + 3]) for j in range(len(vals))])
        f0[idx] = sm
    return f0


def window_features(samples: np.ndarray, sr: int) -> dict:
    """Compute the feature dict for one analysis window of speech."""
    freqs, mag, _ = _spectrogram(samples, sr)
    band = (freqs >= BAND_LO) & (freqs <= BAND_HI)
    mag_b = mag[band]
    rms = _frame_rms(samples, sr, mag.shape[1])

    # Spectral flatness within the speech band.
    flatness = np.exp(np.mean(np.log(mag_b), axis=0)) / np.mean(mag_b, axis=0)

    # Normalised spectral flux within the speech band:
    # ||m_t - m_{t-1}||_1 / ||m_t||_1, averaged over frames.
    if mag_b.shape[1] > 1:
        num = np.sum(np.abs(np.diff(mag_b, axis=1)), axis=0)
        den = np.sum(mag_b[:, 1:], axis=0) + 1e-10
        flux = float(np.mean(num / den))
    else:
        flux = 0.0

    f0 = _f0_track(samples, sr)
    voiced = f0 > 0
    voiced_ratio = float(voiced.mean()) if len(f0) else 0.0
    if voiced.sum() >= 5:
        semis = 12 * np.log2(f0[voiced] / np.median(f0[voiced]))
        f0_semi_std = float(np.std(semis))
    else:
        f0_semi_std = 0.0

    log_energy = 20 * np.log10(rms + 1e-8)
    if voiced.sum() >= 5 and len(log_energy) == len(voiced):
        energy_std = float(np.std(log_energy[voiced]))
    else:
        energy_std = float(np.std(log_energy)) if len(log_energy) else 0.0

    return {
        "voiced_ratio": voiced_ratio,
        "f0_semi_std": f0_semi_std,
        "spectral_flux": flux,
        "energy_std_db": energy_std,
        "spectral_flatness": float(np.mean(flatness)) if len(flatness) else 0.0,
        "duration_s": len(samples) / sr,
    }
