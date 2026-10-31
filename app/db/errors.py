from sqlalchemy.exc import IntegrityError

# SQLSTATE PostgreSQL: unique_violation.
UNIQUE_VIOLATION_SQLSTATE = "23505"


def is_unique_violation(exc: IntegrityError, constraint_name: str) -> bool:
    """True, если PostgreSQL сообщил 23505 именно по этому ограничению."""
    orig = exc.orig
    if getattr(orig, "sqlstate", None) != UNIQUE_VIOLATION_SQLSTATE:
        return False
    driver_error = getattr(orig, "__cause__", None)
    return getattr(driver_error, "constraint_name", None) == constraint_name
