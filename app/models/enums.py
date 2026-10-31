from enum import StrEnum

from sqlalchemy import Enum


class ProjectRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def db_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Строка и CHECK, не тип ENUM в PostgreSQL. В базе лежит .value."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
