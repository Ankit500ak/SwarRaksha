#!/usr/bin/env python
"""Reproducible small eval for the pretrained ML backends (2026-11-12).

What it measures (and nothing more):

1. Speaker verification — LibriSpeech test-clean utterances from 2+
   speakers: ECAPA-TDNN and MFCC embeddings, mean same-speaker vs
   different-speaker cosine over all unordered pairs.
2. Anti-spoofing — the SAME LibriSpeech utterances (bona fide) vs
   LOCALLY SYNTHESISED speech: each utterance's transcript read aloud
   by Piper TTS (neural TTS voice ``en_US-amy-medium`` — a different
   voice from the LibriSpeech speakers; this tests TTS detection, NOT
   voice-clone/conversion detection). Scores from the pretrained
   wav2vec2 checkpoint and, for comparison, the heuristic baseline.
   Reports per-clip scores, accuracy at threshold 0.5, and rank AUC.

Data:
- LibriSpeech test-clean: https://www.openslr.org/resources/12/test-clean.tar.gz
  (downloaded to data/raw/librispeech/ on first run; ~347 MB; the
  selected speakers' files are extracted to data/processed/eval/).
- Piper voice: https://huggingface.co/rhasspy/piper-voices
  (en/en_US/amy/medium; downloaded to data/raw/piper/ on first run).

Run (ML venv, from repo root):
    PYTHONPATH=services/ml-inference:services/voiceprint \
        .venv-ml/bin/python scripts/eval_pretrained.py \
        --out docs/evals/2026-11-12-pretrained-results.json

Requires the heavy ML deps (services/*/requirements-ml.txt) plus
``piper-tts`` for the spoof half. No metric in the output is estimated
or extrapolated — everything is computed from the clips listed in the
JSON. This is a smoke eval on ~20 clips, NOT a benchmark; do not quote
it as one.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import tarfile
import urllib.request
from collections import defaultdict

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRI_TAR = os.path.join(ROOT, "data/raw/librispeech/test-clean.tar.gz")
LIBRI_URL = "https://www.openslr.org/resources/12/test-clean.tar.gz"
EVAL_DIR = os.path.join(ROOT, "data/processed/eval/librispeech")
PIPER_MODEL = os.path.join(ROOT, "data/raw/piper/en_US-amy-medium.onnx")
PIPER_URLS = [
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx",
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
]


def ensure_librispeech(speakers: list[str]) -> None:
    if not os.path.exists(LIBRI_TAR):
        os.makedirs(os.path.dirname(LIBRI_TAR), exist_ok=True)
        print(f"downloading {LIBRI_URL} -> {LIBRI_TAR}", flush=True)
        urllib.request.urlretrieve(LIBRI_URL, LIBRI_TAR)
    marker = os.path.join(EVAL_DIR, ".extracted")
    if os.path.exists(marker):
        return
    os.makedirs(EVAL_DIR, exist_ok=True)
    with tarfile.open(LIBRI_TAR) as tar:
        for m in tar.getmembers():
            parts = m.name.split("/")
            if len(parts) >= 3 and parts[2] in speakers and (
                    m.name.endswith(".flac") or m.name.endswith(".trans.txt")):
                tar.extract(m, EVAL_DIR)
    open(marker, "w").write("ok\n")


def load_eval_utterances(speakers: list[str], per_speaker: int) -> list[dict]:
    """First ``per_speaker`` utterances (sorted by id) per speaker."""
    transcripts: dict[str, str] = {}
    base = os.path.join(EVAL_DIR, "LibriSpeech/test-clean")
    for spk in speakers:
        spk_dir = os.path.join(base, spk)
        for chap in sorted(os.listdir(spk_dir)):
            trans_path = os.path.join(spk_dir, chap, f"{spk}-{chap}.trans.txt")
            if os.path.exists(trans_path):
                for line in open(trans_path):
                    uid, text = line.strip().split(" ", 1)
                    transcripts[uid] = text
    utts = []
    for spk in speakers:
        spk_dir = os.path.join(base, spk)
        files = []
        for chap in sorted(os.listdir(spk_dir)):
            chap_dir = os.path.join(spk_dir, chap)
            files += [os.path.join(chap_dir, f) for f in sorted(os.listdir(chap_dir))
                      if f.endswith(".flac")]
        for path in sorted(files)[:per_speaker]:
            uid = os.path.basename(path)[:-5]
            samples, sr = sf.read(path, dtype="float32", always_2d=False)
            utts.append({"id": uid, "speaker": spk, "path": path,
                         "transcript": transcripts.get(uid, ""),
                         "samples": np.asarray(samples, dtype=np.float32), "sr": sr})
    return utts


def ensure_piper() -> None:
    if os.path.exists(PIPER_MODEL) and os.path.exists(PIPER_MODEL + ".json"):
        return
    os.makedirs(os.path.dirname(PIPER_MODEL), exist_ok=True)
    for url in PIPER_URLS:
        dest = os.path.join(os.path.dirname(PIPER_MODEL), os.path.basename(url))
        print(f"downloading {url} -> {dest}", flush=True)
        urllib.request.urlretrieve(url, dest)


def synthesise_spoof(utts: list[dict]) -> list[dict]:
    """Piper TTS of each transcript — LOCALLY SYNTHESISED spoof clips."""
    import wave

    from piper import PiperVoice

    ensure_piper()
    voice = PiperVoice.load(PIPER_MODEL)
    out_dir = os.path.join(ROOT, "data/processed/eval/tts")
    os.makedirs(out_dir, exist_ok=True)
    spoof = []
    for u in utts:
        path = os.path.join(out_dir, u["id"] + "-piper.wav")
        if not os.path.exists(path):
            with wave.open(path, "wb") as wf:
                voice.synthesize_wav(u["transcript"].capitalize(), wf)
        samples, sr = sf.read(path, dtype="float32", always_2d=False)
        spoof.append({"id": u["id"] + "-piper", "source_utterance": u["id"],
                      "samples": np.asarray(samples, dtype=np.float32), "sr": sr})
    return spoof


def speaker_eval(utts: list[dict]) -> dict:
    from voiceprint import ecapa, embedding as mfcc

    results = {}
    for name, module in (("ecapa", ecapa), ("mfcc", mfcc)):
        embs = [module.embed(u["samples"], u["sr"]) for u in utts]
        same, diff = [], []
        for (i, a), (j, b) in itertools.combinations(enumerate(utts), 2):
            c = module.cosine(embs[i], embs[j])
            (same if a["speaker"] == b["speaker"] else diff).append(round(c, 4))
        results[name] = {
            "embedding_kind": module.EMBEDDING_KIND,
            "embedding_dim": module.EMBEDDING_DIM,
            "same_speaker_pairs": len(same),
            "same_speaker_cosine_mean": round(float(np.mean(same)), 4) if same else None,
            "same_speaker_cosines": same,
            "different_speaker_pairs": len(diff),
            "different_speaker_cosine_mean": round(float(np.mean(diff)), 4) if diff else None,
            "different_speaker_cosines": diff,
        }
    return results


def _auc(scores_pos: list[float], scores_neg: list[float]) -> float | None:
    """Rank AUC: P(score_pos > score_neg) with ties = 0.5."""
    if not scores_pos or not scores_neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0
               for p in scores_pos for n in scores_neg)
    return round(wins / (len(scores_pos) * len(scores_neg)), 4)


def spoof_eval(utts: list[dict], spoof: list[dict]) -> dict:
    import ml_inference.detector as det
    from ml_inference import pretrained_detector

    def _score_with(backend: str, u) -> float | None:
        old = os.environ.get("SWAR_SPOOF_BACKEND")
        os.environ["SWAR_SPOOF_BACKEND"] = backend
        try:
            return det.analyze(u["samples"], u["sr"])["aggregate_spoof"]
        finally:
            if old is None:
                os.environ.pop("SWAR_SPOOF_BACKEND", None)
            else:
                os.environ["SWAR_SPOOF_BACKEND"] = old

    def pretrained_score(u):
        return _score_with("pretrained", u)

    def heuristic_score(u):
        return _score_with("heuristic", u)

    out = {"pretrained_model_version": pretrained_detector.MODEL_VERSION}
    for name, scorer in (("pretrained", pretrained_score), ("heuristic", heuristic_score)):
        bona = [{"id": u["id"], "aggregate_spoof": scorer(u)} for u in utts]
        fake = [{"id": s["id"], "aggregate_spoof": scorer(s)} for s in spoof]
        b = [x["aggregate_spoof"] for x in bona if x["aggregate_spoof"] is not None]
        f = [x["aggregate_spoof"] for x in fake if x["aggregate_spoof"] is not None]
        correct = sum(1 for x in b if x < 0.5) + sum(1 for x in f if x >= 0.5)
        total = len(b) + len(f)
        out[name] = {
            "bona_fide": bona, "spoof": fake,
            "bona_fide_mean": round(float(np.mean(b)), 4) if b else None,
            "spoof_mean": round(float(np.mean(f)), 4) if f else None,
            "accuracy_at_0.5": round(correct / total, 4) if total else None,
            "auc_spoof_vs_bona_fide": _auc(f, b),
            "n_bona_fide_scored": len(b), "n_spoof_scored": len(f),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--speakers", default="1089,1188",
                    help="comma-separated LibriSpeech test-clean speaker ids")
    ap.add_argument("--per-speaker", type=int, default=5)
    ap.add_argument("--out", default=None, help="write JSON results here")
    ap.add_argument("--skip-spoof", action="store_true")
    args = ap.parse_args()

    speakers = [s.strip() for s in args.speakers.split(",") if s.strip()]
    ensure_librispeech(speakers)
    utts = load_eval_utterances(speakers, args.per_speaker)
    print(f"loaded {len(utts)} utterances from speakers {speakers}", flush=True)

    results: dict = {
        "dataset": {
            "name": "LibriSpeech test-clean",
            "url": LIBRI_URL,
            "speakers": speakers,
            "utterances": [{"id": u["id"], "speaker": u["speaker"],
                            "duration_sec": round(len(u["samples"]) / u["sr"], 2)}
                           for u in utts],
        },
        "speaker_verification": speaker_eval(utts),
    }
    if not args.skip_spoof:
        spoof = synthesise_spoof(utts)
        results["spoof_source"] = {
            "kind": "locally synthesised speech (NOT a public spoof corpus)",
            "tool": "Piper TTS, voice en_US-amy-medium (rhasspy/piper-voices)",
            "note": "Same transcripts as the bona fide clips, read by a "
                    "neural TTS voice that is NOT either LibriSpeech speaker. "
                    "Tests TTS detection only — not voice conversion/cloning.",
            "clips": [{"id": s["id"], "source_utterance": s["source_utterance"],
                       "duration_sec": round(len(s["samples"]) / s["sr"], 2)}
                      for s in spoof],
        }
        results["anti_spoofing"] = spoof_eval(utts, spoof)

    text = json.dumps(results, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
