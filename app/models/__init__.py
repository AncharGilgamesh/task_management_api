"""Импорт моделей, чтобы Alembic видел metadata."""

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.task import Task
from app.models.task_status_history import TaskStatusHistory
from app.models.user import User

__all__ = [
    "Project",
    "ProjectMember",
    "Task",
    "TaskStatusHistory",
    "User",
]
