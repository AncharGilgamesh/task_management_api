import asyncpg
from sqlalchemy.dialects.postgresql.asyncpg import (
    AsyncAdapt_asyncpg_connection,
    PGDialect_asyncpg,
)
from sqlalchemy.exc import IntegrityError

_dbapi = PGDialect_asyncpg.import_dbapi()


def make_pg_integrity_error(
    sqlstate: str,
    constraint_name: str | None,
    *,
    hide_parameters: bool = True,
) -> IntegrityError:

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
