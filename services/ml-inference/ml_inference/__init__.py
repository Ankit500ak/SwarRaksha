"""SwarRaksha ML inference package.

Anti-spoofing backends are selected by ``SWAR_SPOOF_BACKEND``
(``heuristic`` default, ``pretrained`` for the wav2vec2 checkpoint) —
see ``detector.py``. ``MODEL_VERSION`` remains the heuristic version
string for backwards compatibility; use ``active_model_version()``
(or the ``model_version`` field of ``analyze()`` results) for the
version of the backend that is actually selected.
"""
from .audio_io import load_audio, load_audio_file, TARGET_SR
from .detector import (MODEL_VERSION, WINDOW_SEC, active_model_version,
                       analyze, backend_name, score_window)

__all__ = ["load_audio", "load_audio_file", "TARGET_SR",
           "analyze", "score_window", "MODEL_VERSION", "WINDOW_SEC",
           "active_model_version", "backend_name"]
