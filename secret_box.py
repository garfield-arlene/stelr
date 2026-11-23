"""Encrypt small secrets (e.g. third-party API keys) before they're stored.

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a key
derived from the server's SECRET_KEY, so a copy of the database or data
volume on its own doesn't reveal them. Anyone who also has SECRET_KEY can
decrypt them, which is unavoidable for a secret the server must use.

If SECRET_KEY changes, previously stored secrets can no longer be
decrypted and have to be entered again.
"""
import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

DEFAULT_SECRET_KEY = "stelr-secret-change-me"
PREFIX = "enc:v1:"
MIN_SECRET_KEY_LENGTH = 32


class SecretBoxError(Exception):
    pass


def _secret_key() -> str:
    return os.environ.get("SECRET_KEY", DEFAULT_SECRET_KEY)


def secret_key_is_strong() -> bool:
    """False when SECRET_KEY is the public default or too short to trust."""
    key = _secret_key()
    return key != DEFAULT_SECRET_KEY and len(key) >= MIN_SECRET_KEY_LENGTH


def _fernet() -> Fernet:
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=b"stelr-secret-box-v1").derive(_secret_key().encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(plaintext: str) -> str:
    if not secret_key_is_strong():
        raise SecretBoxError(
            "SECRET_KEY is the default or shorter than "
            f"{MIN_SECRET_KEY_LENGTH} characters, so it can't protect stored secrets.")
    return PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def decrypt(stored: str) -> str:
    if not stored.startswith(PREFIX):
        raise SecretBoxError("Stored value isn't encrypted.")
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
    except InvalidToken:
        raise SecretBoxError(
            "Stored secret can't be decrypted. SECRET_KEY has probably changed; "
            "enter the secret again.")
