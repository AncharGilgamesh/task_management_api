from app.core.security import hash_password, verify_password


def test_hash_password() -> None:
    hashed = hash_password("my-secret-password")

    assert hashed != "my-secret-password"
    assert hashed.startswith("$argon2")


def test_verify_password() -> None:
    hashed = hash_password("my-secret-password")

    assert verify_password("my-secret-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False
