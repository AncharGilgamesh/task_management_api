from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import TaskPriority, TaskStatus

TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

AssigneeId = Annotated[int, Field(ge=1, le=2_147_483_647)]


def _empty_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


TaskDescription = Annotated[
    Annotated[str, StringConstraints(max_length=5000)] | None,
    BeforeValidator(_empty_to_none),
]


class TaskCreate(BaseModel):
    """Новая задача. Статус, автор и проект задаёт сервер."""

    model_config = ConfigDict(extra="forbid")

    title: TaskTitle
    description: TaskDescription = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: datetime | None = None
    assignee_id: AssigneeId | None = None


class TaskUpdate(BaseModel):
    """Меняются только переданные поля."""

    model_config = ConfigDict(extra="forbid")

    title: TaskTitle | None = None
    description: TaskDescription = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    assignee_id: AssigneeId | None = None
    status: TaskStatus | None = None

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("priority cannot be null")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null")
        return self


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: datetime | None
    project_id: int
    author_id: int
    assignee_id: int | None
    created_at: datetime
    updated_at: datetime


class TaskStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    old_status: TaskStatus | None
    new_status: TaskStatus
    changed_by_id: int | None
    changed_at: datetime
