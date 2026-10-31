from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TaskPriority, TaskStatus, db_enum
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task_status_history import TaskStatusHistory
    from app.models.user import User


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # Покрывает и фильтр по project_id, и по (project_id, status).
        Index("ix_tasks_project_id_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        db_enum(TaskStatus, "task_status"),
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        db_enum(TaskPriority, "task_priority"),
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")
    author: Mapped["User"] = relationship(
        back_populates="created_tasks",
        foreign_keys=[author_id],
    )
    assignee: Mapped["User | None"] = relationship(
        back_populates="assigned_tasks",
        foreign_keys=[assignee_id],
    )
    status_history: Mapped[list["TaskStatusHistory"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TaskStatusHistory.changed_at",
    )
