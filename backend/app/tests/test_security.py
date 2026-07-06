from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-Pass!")
    assert hashed != "s3cret-Pass!"
    assert verify_password("s3cret-Pass!", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    token = create_access_token(subject="42", extra_claims={"role": "admin"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_decode_invalid_token_returns_none():
    assert decode_access_token("not-a-valid-token") is None
