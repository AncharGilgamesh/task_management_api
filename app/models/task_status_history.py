from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TaskStatus, db_enum

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"
    __table_args__ = (
        Index("ix_task_status_history_task_id_changed_at", "task_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
    )
    # NULL у первой записи — при создании задачи предыдущего статуса нет.
    old_status: Mapped[TaskStatus | None] = mapped_column(
        db_enum(TaskStatus, "old_status"),
    )
    new_status: Mapped[TaskStatus] = mapped_column(
        db_enum(TaskStatus, "new_status"),
    )
    # SET NULL: история сохраняется, даже если пользователя удалили.
    changed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    task: Mapped["Task"] = relationship(back_populates="status_history")
    changed_by: Mapped["User | None"] = relationship()
