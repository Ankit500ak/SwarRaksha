"""Upload validation for audio endpoints (checks + voiceprints).

Checks, in order: size cap, extension allowlist, content sniff against
the file signature, and — where soundfile can read the container —
a duration cap. Rejections raise HTTPException with a plain message;
main.py renders them in the consistent {code, message} shape.
"""
from __future__ import annotations

import io
import os

from fastapi import HTTPException

from .config import MAX_CLIP_SECONDS, MAX_UPLOAD_BYTES

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac"}

# Magic-byte signatures per extension family.
def _sniff_ok(ext: str, data: bytes) -> bool:
    if ext == ".wav":
        return data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if ext == ".mp3":
        return data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF
                                       and (data[1] & 0xE0) == 0xE0)
    if ext == ".ogg":
        return data[:4] == b"OggS"
    if ext == ".webm":
        return data[:4] == b"\x1a\x45\xdf\xa3"
    if ext == ".m4a":
        return len(data) > 8 and data[4:8] == b"ftyp"
    if ext == ".flac":
        return data[:4] == b"fLaC"
    return False


def validate_audio(data: bytes, filename: str | None,
                   *, max_bytes: int = MAX_UPLOAD_BYTES,
                   max_seconds: float = MAX_CLIP_SECONDS) -> None:
    if len(data) == 0:
        raise HTTPException(400, "Empty audio upload")
    if len(data) > max_bytes:
        raise HTTPException(413, "Audio file too large")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported audio type '{ext or '(none)'}'; "
                                 "allowed: wav, mp3, ogg, webm, m4a, flac")
    if not _sniff_ok(ext, data):
        raise HTTPException(400, "Audio content does not match its file type")
    # Duration cap where the container is readable by soundfile (wav/flac/
    # ogg/mp3 usually are; webm/m4a often are not — for those the decoded
    # length is still truncated downstream in the check pipeline).
    try:
        import soundfile as sf
        info = sf.info(io.BytesIO(data))
        if info.samplerate and info.frames / float(info.samplerate) > max_seconds:
            raise HTTPException(400, f"Audio longer than {int(max_seconds)} seconds")
    except HTTPException:
        raise
    except Exception:
        pass
