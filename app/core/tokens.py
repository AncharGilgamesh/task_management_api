import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings

# Алгоритм из заголовка токена не принимаем.
ALGORITHM = "HS256"

REQUIRED_CLAIMS = ["sub", "exp", "iat", "jti"]


class InvalidTokenError(Exception):
    """Токен не подошёл."""


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Access token: id пользователя и служебные поля."""
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """Id пользователя из `sub`. Любая ошибка токена — InvalidTokenError."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError:
        raise InvalidTokenError from None

    subject = payload["sub"]
    if not (isinstance(subject, str) and subject.isascii() and subject.isdigit()):
        raise InvalidTokenError
    return int(subject)
