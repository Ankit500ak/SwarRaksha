"""Verdict fusion — PLAN.md Section 5, implemented as specified.

Signals: (a) per-window spoof scores, (b) voiceprint cosine similarity
against the claimed identity, (c) an optional challenge result.

Rules (from the plan):
- RED  if spoof > 0.8 sustained over 2+ speech windows, regardless of
  voiceprint. Also RED if the average spoof alone is > 0.8.
- GREEN requires mean spoof < 0.3 AND voiceprint similarity at/above
  threshold. Without a claimed voiceprint, a check can never be GREEN —
  "sounds human" is not "is your son".
- Everything else is YELLOW ("be careful"), including no-speech audio.

Reason strings are plain-language English; the web app maps the codes
to Hindi for the verdict screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SPOOF_RED = 0.8
SPOOF_GREEN_MAX = 0.3


@dataclass
class FusionResult:
    verdict: str            # green | yellow | red
    risk_score: float       # 0..1
    reasons: list[dict] = field(default_factory=list)  # {code, text}


def _reason(code: str, text: str) -> dict:
    return {"code": code, "text": text}


def fuse(window_scores: list[float | None],
         voiceprint_similarity: float | None,
         vp_threshold: float,
         challenge_result: str | None = None) -> FusionResult:
    scored = [s for s in window_scores if s is not None]
    reasons: list[dict] = []

    if not scored:
        return FusionResult("yellow", 0.5, [_reason(
            "no_speech",
            "We could not hear enough clear speech in this audio to judge it. Treat the caller as unverified.")])

    mean_spoof = sum(scored) / len(scored)
    hot_windows = sum(1 for s in scored if s > SPOOF_RED)

    # --- risk score: spoof-dominant blend -------------------------------
    risk = mean_spoof
    if voiceprint_similarity is not None:
        # Map similarity 0.3..1.0 -> mismatch 1..0
        mismatch = min(1.0, max(0.0, (1.0 - voiceprint_similarity) / 0.7))
        risk = 0.65 * mean_spoof + 0.35 * mismatch
    if challenge_result == "failed":
        risk = max(risk, 0.85)
    elif challenge_result == "passed":
        risk = min(risk, 0.45)
    risk = round(min(1.0, max(0.0, risk)), 4)

    # --- RED -------------------------------------------------------------
    if hot_windows >= 2 or mean_spoof > SPOOF_RED:
        reasons.append(_reason(
            "synthetic_sustained",
            "The voice shows strong signs of being computer-made across several moments of the audio."))
        if voiceprint_similarity is not None and voiceprint_similarity >= vp_threshold:
            reasons.append(_reason(
                "vp_match_but_synthetic",
                "It resembles the enrolled voice, which is exactly how voice-clone scams work — a matching sound does not make it safe."))
        return FusionResult("red", risk, reasons)
    if challenge_result == "failed" and mean_spoof > 0.5:
        reasons.append(_reason(
            "challenge_failed",
            "The caller could not pass the safety challenge, and the voice already sounded suspicious."))
        return FusionResult("red", risk, reasons)

    # --- signal narration for non-red verdicts ---------------------------
    if mean_spoof >= 0.5:
        reasons.append(_reason(
            "synthetic_some",
            "Some moments of this voice sound computer-made, but not strongly enough to be sure."))
    elif mean_spoof >= SPOOF_GREEN_MAX:
        reasons.append(_reason(
            "synthetic_mild",
            "The voice sounds mostly human, with mild signs that keep us from fully trusting it."))
    else:
        reasons.append(_reason(
            "sounds_human",
            "The voice sounds human — we found no strong signs of computer-made speech."))

    vp_ok = voiceprint_similarity is not None and voiceprint_similarity >= vp_threshold
    if voiceprint_similarity is not None and not vp_ok:
        reasons.append(_reason(
            "vp_mismatch",
            "The voice does not match the enrolled voiceprint of the person it claims to be."))
    if voiceprint_similarity is not None and vp_ok:
        reasons.append(_reason(
            "vp_match",
            "The voice matches the enrolled voiceprint."))
    if voiceprint_similarity is None:
        reasons.append(_reason(
            "vp_none",
            "No enrolled voice was claimed for this check, so the caller's identity itself is unverified."))

    # --- GREEN -------------------------------------------------------------
    if mean_spoof < SPOOF_GREEN_MAX and vp_ok:
        return FusionResult("green", risk, reasons)

    # --- YELLOW ------------------------------------------------------------
    return FusionResult("yellow", risk, reasons)
