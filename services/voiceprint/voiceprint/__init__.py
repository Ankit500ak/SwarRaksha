"""SwarRaksha voiceprint package.

The active backend is selected by ``SWAR_VOICEPRINT_BACKEND``
(``mfcc`` default, ``ecapa`` for the pretrained ECAPA-TDNN model) —
see ``factory.py``. This package re-exports the selected backend's
interface so existing imports keep working:

    from voiceprint import embed, enroll, cosine, to_bytes, from_bytes
    from voiceprint import EMBEDDING_DIM, EMBEDDING_KIND

Importing this package never loads torch or downloads model weights;
the ECAPA checkpoint loads lazily on the first ``embed()`` call.
Direct module imports also keep working and are backend-specific:
``voiceprint.embedding`` is always the MFCC baseline and
``voiceprint.ecapa`` is always the ECAPA backend.
"""
from .factory import backend_name, get_backend

_backend = get_backend()

embed = _backend.embed
enroll = _backend.enroll
cosine = _backend.cosine
to_bytes = _backend.to_bytes
from_bytes = _backend.from_bytes
EMBEDDING_DIM = _backend.EMBEDDING_DIM
EMBEDDING_KIND = _backend.EMBEDDING_KIND
BACKEND = backend_name()

__all__ = ["embed", "enroll", "cosine", "to_bytes", "from_bytes",
           "EMBEDDING_DIM", "EMBEDDING_KIND", "BACKEND",
           "backend_name", "get_backend"]
