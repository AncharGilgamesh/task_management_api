import pytest
from pydantic import ValidationError

from app.core.config import SECRET_KEY_MIN_LENGTH, Settings

DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


def make_settings(**overrides: object) -> Settings:
    # _env_file=None: тест не должен читать настоящий .env разработчика.
    return Settings(_env_file=None, database_url=DATABASE_URL, **overrides)


def test_secret_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        make_settings()

    assert "secret_key" in str(exc_info.value)


def test_short_secret_key() -> None:
    secret = "short"
    with pytest.raises(ValidationError) as exc_info:
        make_settings(secret_key=secret)

    message = str(exc_info.value)
    assert f"SECRET_KEY must be at least {SECRET_KEY_MIN_LENGTH} characters" in message
    assert "secrets.token_urlsafe" in message


