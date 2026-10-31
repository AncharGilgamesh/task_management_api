import pytest
from pydantic import ValidationError

from app.models.enums import TaskPriority
from app.schemas.task import TaskCreate, TaskUpdate


def assert_invalid(model: type[TaskCreate] | type[TaskUpdate], data: dict) -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(data)
    return exc_info.value


def test_create_trims_title() -> None:
    task = TaskCreate.model_validate({"title": "  Fix login  "})

    assert task.title == "Fix login"
    assert task.description is None
    assert task.priority is TaskPriority.MEDIUM
    assert task.due_date is None
    assert task.assignee_id is None
    assert set(task.model_dump()) == {"title", "description", "priority", "due_date", "assignee_id"}
    assert "status" not in task.model_dump()
    assert "author_id" not in task.model_dump()
    assert "project_id" not in task.model_dump()


def test_create_bad_title() -> None:
    title = ""
    assert_invalid(TaskCreate, {"title": title})


def test_create_rejects_status() -> None:
    assert_invalid(TaskCreate, {"title": "T", "status": "todo"})


