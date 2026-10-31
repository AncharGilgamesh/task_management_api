import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import jwt
from sqlalchemy.dialects.postgresql.asyncpg import (
    AsyncAdapt_asyncpg_connection,
    PGDialect_asyncpg,
)
from sqlalchemy.exc import IntegrityError

from app.core.config import settings

_dbapi = PGDialect_asyncpg.import_dbapi()


def make_pg_integrity_error(
    sqlstate: str,
    constraint_name: str | None,
    *,
    hide_parameters: bool = True,
) -> IntegrityError:
    """IntegrityError как от SQLAlchemy и asyncpg, без живой базы."""
    fields = {
        "C": sqlstate,
        "M": f'violation of constraint "{constraint_name}"',
        "D": "Key (email)=(secret@example.com) already exists.",
    }
    if constraint_name is not None:
        fields["n"] = constraint_name
    driver_error = asyncpg.exceptions.PostgresError.new(fields)
    try:
        AsyncAdapt_asyncpg_connection._handle_exception_no_connection(_dbapi, driver_error)
    except Exception as translated:
        return IntegrityError(
            "INSERT INTO users ...",
            {"hashed_password": "$argon2id$secret-hash"},
            translated,
            hide_parameters=hide_parameters,
        )
    raise AssertionError("asyncpg error was not translated")


def make_jwt(
    user_id: object = 1,
    *,
    expires_in: timedelta = timedelta(minutes=5),
    key: str | None = None,
    algorithm: str = "HS256",
    extra: dict | None = None,
    omit: tuple[str, ...] = (),
) -> str:
    """Собирает JWT вручную (в обход create_access_token) для проверки отказов."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id) if isinstance(user_id, int) else user_id,
        "iat": now,
        "exp": now + expires_in,
        "jti": uuid.uuid4().hex,
        **(extra or {}),
    }
    for claim in omit:
        payload.pop(claim)
    signing_key = settings.secret_key.get_secret_value() if key is None else key
    return jwt.encode(payload, signing_key, algorithm=algorithm)