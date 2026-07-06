"""Symmetric encryption for sensitive fields stored in the database (e.g. mailbox passwords).

Uses Fernet (AES128-CBC + HMAC) with a key supplied via the ENCRYPTION_KEY env var.
Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class EncryptionError(Exception):
    pass


@lru_cache
def _get_fernet() -> Fernet:
    if not settings.encryption_key:
        raise EncryptionError(
            "ENCRYPTION_KEY is not configured. Set it in the environment before storing secrets."
        )
    try:
        return Fernet(settings.encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise EncryptionError("ENCRYPTION_KEY must be a valid urlsafe base64 32-byte key.") from exc


def encrypt_value(plain_value: str) -> str:
    return _get_fernet().encrypt(plain_value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted_value.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError("Unable to decrypt value: invalid token or wrong key.") from exc
