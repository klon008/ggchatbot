"""Подпись ссылки альбома и шифрование URL API (AES-256-GCM)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Optional
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .constants import ALBUM_TOKEN_TTL_SEC

_NONCE_LEN = 12


def _derive_aes_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def sign_album_token(secret: str, nick_lower: str, exp: int) -> str:
    payload = f"{nick_lower}:{exp}"
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(digest)[:16]


def verify_album_token(secret: str, nick_lower: str, exp: int, token: str) -> bool:
    if exp < int(time.time()):
        return False
    expected = sign_album_token(secret, nick_lower, exp)
    return hmac.compare_digest(expected, token)


def encode_api_url(secret: str, api_base_url: str) -> str:
    """Зашифровать публичный URL CLO → base64url (буквы, цифры, -, _)."""
    url = api_base_url.rstrip("/")
    key = _derive_aes_key(secret)
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(key).encrypt(nonce, url.encode("utf-8"), None)
    return _b64url_encode(nonce + ciphertext)


def decode_api_url(secret: str, encoded: str) -> Optional[str]:
    try:
        raw = _b64url_decode(encoded)
        if len(raw) < _NONCE_LEN + 1:
            return None
        nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        key = _derive_aes_key(secret)
        plain = AESGCM(key).decrypt(nonce, ciphertext, None)
        return plain.decode("utf-8").rstrip("/")
    except Exception:
        return None


def build_album_url(
    *,
    site_base_url: str,
    link_secret: str,
    nick: str,
    api_base_url: str,
    ttl_sec: int = ALBUM_TOKEN_TTL_SEC,
) -> str:
    nick_lower = nick.strip().lower()
    exp = int(time.time()) + ttl_sec
    k = sign_album_token(link_secret, nick_lower, exp)
    api_enc = encode_api_url(link_secret, api_base_url)
    base = site_base_url.rstrip("/")
    params = urlencode(
        {
            "u": nick_lower,
            "k": k,
            "exp": str(exp),
            "api": api_enc,
        },
        quote_via=quote,
    )
    return f"{base}/?{params}"
