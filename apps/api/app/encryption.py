"""Voiceprint embedding encryption at rest (PLAN.md §11).

Storage format (versioned, self-describing):
  * ``b"v1:" + nonce(12) + AES-256-GCM ciphertext+tag`` when the
    ``cryptography`` package is available (the production path; it is in
    apps/api/requirements.txt).
  * ``b"v1h:" + salt(16) + nonce(16) + ciphertext + HMAC-SHA256 tag(32)``
    — documented INTERIM fallback used only when ``cryptography`` is not
    installed: an encrypt-then-MAC construction from stdlib primitives
    (HMAC-SHA256 in counter mode as keystream, independent MAC key via
    HKDF-style HMAC domain separation). Prefer the AES-GCM path; this
    exists so dev/test environments without the wheel still never store
    plaintext embeddings.
  * Anything without a known prefix is a LEGACY plain float blob written
    before encryption shipped; it is returned unchanged on read so old
    rows keep working, and is re-encrypted on next write.

Key: VOICEPRINT_ENC_KEY env, base64-encoded 32 bytes. In dev, when the
variable is absent, the key is derived from JWT_SECRET via SHA-256 —
documented dev fallback only; production refuses to boot without a real
key (see config.validate_config).
"""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import os
import secrets

from . import config

_PREFIX_AES = b"v1:"
_PREFIX_HMAC = b"v1h:"

try:  # production path
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_AESGCM = True
except Exception:  # pragma: no cover - depends on environment
    AESGCM = None  # type: ignore
    _HAS_AESGCM = False


def get_key() -> bytes:
    raw = config.VOICEPRINT_ENC_KEY or os.environ.get("VOICEPRINT_ENC_KEY", "")
    if raw:
        key = config.decode_enc_key(raw)
        if key is None:
            raise ValueError("VOICEPRINT_ENC_KEY is not a base64 32-byte key")
        return key
    if config.SWAR_ENV == "production":
        raise ValueError("VOICEPRINT_ENC_KEY is required in production")
    # Dev fallback: deterministic key derived from the (dev) JWT secret.
    return hashlib.sha256(("swarraksha-vp-dev:" + config.JWT_SECRET).encode()).digest()


def is_encrypted(blob: bytes | None) -> bool:
    return bool(blob) and (blob.startswith(_PREFIX_AES) or blob.startswith(_PREFIX_HMAC))


# --- interim stdlib construction -------------------------------------------
def _hmac_keys(master: bytes, salt: bytes) -> tuple[bytes, bytes]:
    enc = hmac_mod.new(master, b"swar-vp-enc" + salt, hashlib.sha256).digest()
    mac = hmac_mod.new(master, b"swar-vp-mac" + salt, hashlib.sha256).digest()
    return enc, mac


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        out.extend(hmac_mod.new(key, nonce + counter.to_bytes(8, "big"),
                                hashlib.sha256).digest())
        counter += 1
    return bytes(out[:n])


def _encrypt_hmac(key: bytes, plain: bytes) -> bytes:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    enc_key, mac_key = _hmac_keys(key, salt)
    ks = _keystream(enc_key, nonce, len(plain))
    ct = bytes(a ^ b for a, b in zip(plain, ks))
    tag = hmac_mod.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    return _PREFIX_HMAC + salt + nonce + ct + tag


def _decrypt_hmac(key: bytes, blob: bytes) -> bytes:
    body = blob[len(_PREFIX_HMAC):]
    salt, nonce, tag = body[:16], body[16:32], body[-32:]
    ct = body[32:-32]
    enc_key, mac_key = _hmac_keys(key, salt)
    expected = hmac_mod.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
    if not hmac_mod.compare_digest(expected, tag):
        raise ValueError("voiceprint ciphertext failed integrity check")
    ks = _keystream(enc_key, nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks))


# --- public API --------------------------------------------------------------
def encrypt_embedding(plain: bytes) -> bytes:
    key = get_key()
    if _HAS_AESGCM:
        nonce = secrets.token_bytes(12)
        return _PREFIX_AES + nonce + AESGCM(key).encrypt(nonce, plain, None)
    return _encrypt_hmac(key, plain)


def decrypt_embedding(blob: bytes) -> bytes:
    """Decrypt a stored blob; legacy plain blobs pass through unchanged."""
    if blob.startswith(_PREFIX_AES):
        if not _HAS_AESGCM:
            raise ValueError("AES-GCM ciphertext but 'cryptography' is not installed")
        body = blob[len(_PREFIX_AES):]
        return AESGCM(get_key()).decrypt(body[:12], body[12:], None)
    if blob.startswith(_PREFIX_HMAC):
        return _decrypt_hmac(get_key(), blob)
    return blob  # legacy plain format (pre-encryption rows)


def generate_key_b64() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()
