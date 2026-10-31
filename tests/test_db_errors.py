from app.db.errors import is_unique_violation
from tests.helpers import make_pg_integrity_error


def test_unique_violation() -> None:
    exc = make_pg_integrity_error("23505", "uq_users_email")

    assert is_unique_violation(exc, "uq_users_email") is True


