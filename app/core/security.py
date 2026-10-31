import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

password_hash = PasswordHash((Argon2Hasher(),))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


# Чтобы вход с неизвестным email занимал столько же, сколько проверка настоящего пароля.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
