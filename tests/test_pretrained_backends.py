"""Backend-selection tests for the pretrained ML lane.

These run in the BASE venv (no torch): they verify that defaults are
unchanged, that selecting a pretrained backend never loads weights at
import time, and that actually *using* a pretrained backend without
its heavy deps fails loudly and honestly (never silently falls back
while reporting the wrong model_version).
"""
import importlib
import os
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS = [os.path.join(ROOT, p) for p in
         ("services/ml-inference", "services/voiceprint", "apps/api")]


def _run(code: str, env_extra: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(PATHS)
    env.update(env_extra)
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, timeout=120)


def test_default_voiceprint_backend_is_mfcc():
    import voiceprint

    assert voiceprint.BACKEND == "mfcc"
    assert voiceprint.EMBEDDING_KIND == "mfcc-stats-v0"
    assert voiceprint.EMBEDDING_DIM == 44


def test_default_spoof_backend_is_heuristic():
    from ml_inference import detector

    assert detector.backend_name() == "heuristic"
    assert detector.active_model_version() == "baseline-heuristic-v0"


def test_ecapa_module_import_is_lazy_and_correct_interface():
    """Importing the ECAPA module must not require torch or weights."""
    from voiceprint import ecapa

    assert ecapa.EMBEDDING_DIM == 192
    assert ecapa.EMBEDDING_KIND == "ecapa-tdnn-voxceleb-v1"
    for fn in ("embed", "enroll", "cosine", "to_bytes", "from_bytes"):
        assert callable(getattr(ecapa, fn))
    a = np.arange(192, dtype=np.float32)
    assert ecapa.from_bytes(ecapa.to_bytes(a)).shape == (192,)
    with pytest.raises(ValueError):
        ecapa.from_bytes(np.zeros(44, dtype=np.float32).tobytes())
    with pytest.raises(ValueError):
        ecapa.cosine(np.zeros(192, dtype=np.float32), np.zeros(44, dtype=np.float32))


def test_pretrained_detector_module_import_is_lazy():
    from ml_inference import pretrained_detector

    assert pretrained_detector.MODEL_VERSION == \
        "pretrained-aasist:clovaai/aasist AASIST.pth (ASVspoof2019-LA)"
    short = pretrained_detector.score_window(np.zeros(100, dtype=np.float32), 16000)
    assert short["spoof_score"] is None
    assert short["sufficient_speech"] is False


def test_ecapa_selection_boots_without_torch():
    """SWAR_VOICEPRINT_BACKEND=ecapa must import fine; only embed()
    may fail (loudly) when torch is absent."""
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("torch is installed in this venv; absence case n/a")
    proc = _run(
        "import voiceprint\n"
        "assert voiceprint.BACKEND == 'ecapa'\n"
        "assert voiceprint.EMBEDDING_DIM == 192\n"
        "print('boot-ok')\n",
        {"SWAR_VOICEPRINT_BACKEND": "ecapa"})
    assert proc.returncode == 0, proc.stderr
    assert "boot-ok" in proc.stdout

    proc = _run(
        "import numpy as np\n"
        "from voiceprint import ecapa\n"
        "ecapa.embed(np.zeros(16000, dtype=np.float32), 16000)\n",
        {"SWAR_VOICEPRINT_BACKEND": "ecapa"})
    assert proc.returncode != 0
    assert "requirements-ml.txt" in proc.stderr


def test_pretrained_selection_fails_loudly_without_torch():
    if importlib.util.find_spec("torch") is not None:
        pytest.skip("torch is installed in this venv; absence case n/a")
    proc = _run(
        "import numpy as np\n"
        "from ml_inference.detector import analyze\n"
        "analyze(np.zeros(16000, dtype=np.float32), 16000)\n",
        {"SWAR_SPOOF_BACKEND": "pretrained"})
    assert proc.returncode != 0
    assert "requirements-ml.txt" in proc.stderr


def test_unknown_backends_rejected():
    proc = _run("import voiceprint\n", {"SWAR_VOICEPRINT_BACKEND": "nope"})
    assert proc.returncode != 0
    proc = _run(
        "from ml_inference.detector import backend_name\nbackend_name()\n",
        {"SWAR_SPOOF_BACKEND": "nope"})
    assert proc.returncode != 0
