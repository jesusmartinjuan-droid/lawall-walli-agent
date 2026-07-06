import pytest

from app.core.encryption import EncryptionError, decrypt_value, encrypt_value


def test_encrypt_decrypt_roundtrip():
    plain = "super-secret-imap-password"
    encrypted = encrypt_value(plain)
    assert encrypted != plain
    assert decrypt_value(encrypted) == plain


def test_decrypt_invalid_token_raises():
    with pytest.raises(EncryptionError):
        decrypt_value("not-a-valid-fernet-token")
