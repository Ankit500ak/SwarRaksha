"""Voiceprint backend selection.

``SWAR_VOICEPRINT_BACKEND`` selects the speaker-embedding backend:

- ``mfcc`` (default): the untrained MFCC-statistics baseline in
  ``embedding.py`` (44-dim). No heavy deps.
- ``ecapa``: the pretrained ECAPA-TDNN backend in ``ecapa.py``
  (192-dim, SpeechBrain ``speechbrain/spkrec-ecapa-voxceleb``).
  Requires the heavy deps in ``requirements-ml.txt``; the model itself
  is lazy-loaded on first ``embed()`` call, so importing the package
  never downloads weights and the API boots without torch.

``voiceprint/__init__.py`` re-exports the selected backend's symbols so
existing call sites (``from voiceprint import embed, enroll, cosine,
to_bytes, from_bytes, EMBEDDING_KIND``) keep working unchanged.
"""
from __future__ import annotations

import importlib
import os

BACKEND_ENV = "SWAR_VOICEPRINT_BACKEND"
DEFAULT_BACKEND = "mfcc"
_MODULES = {"mfcc": ".embedding", "ecapa": ".ecapa"}


def backend_name() -> str:
    name = os.environ.get(BACKEND_ENV, DEFAULT_BACKEND).strip().lower()
    if name not in _MODULES:
        raise ValueError(
            f"unknown {BACKEND_ENV}={name!r}; expected one of {sorted(_MODULES)}")
    return name


def get_backend():
    """Return the module implementing the selected backend."""
    return importlib.import_module(_MODULES[backend_name()], __package__)
