"""Verdict fusion state machine — PLAN.md Section 5 rules."""
from app.fusion import fuse

THR = 0.80


def test_red_sustained_spoof_overrides_voiceprint_match():
    r = fuse([0.9, 0.85, 0.4], 0.99, THR)
    assert r.verdict == "red"
    assert any(x["code"] == "synthetic_sustained" for x in r.reasons)


def test_red_mean_spoof_alone():
    r = fuse([0.95], None, THR)
    assert r.verdict == "red"


def test_green_needs_low_spoof_and_vp_match():
    r = fuse([0.1, 0.2], 0.95, THR)
    assert r.verdict == "green"


def test_no_voiceprint_never_green():
    r = fuse([0.05, 0.1], None, THR)
    assert r.verdict == "yellow"
    assert any(x["code"] == "vp_none" for x in r.reasons)


def test_vp_mismatch_is_yellow():
    r = fuse([0.1], 0.30, THR)
    assert r.verdict == "yellow"
    assert any(x["code"] == "vp_mismatch" for x in r.reasons)


def test_no_speech_is_yellow():
    r = fuse([None, None], None, THR)
    assert r.verdict == "yellow"
    assert r.reasons[0]["code"] == "no_speech"


def test_challenge_failed_plus_suspicion_is_red():
    r = fuse([0.6, 0.55], None, THR, challenge_result="failed")
    assert r.verdict == "red"


def test_mild_spoof_matching_vp_is_yellow_not_green():
    r = fuse([0.45, 0.4], 0.95, THR)
    assert r.verdict == "yellow"
