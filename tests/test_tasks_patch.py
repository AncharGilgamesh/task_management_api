from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, Task, TaskStatusHistory, User
from app.models.enums import ProjectRole, TaskPriority, TaskStatus

pytestmark = pytest.mark.anyio

FORBIDDEN = {"detail": "Not enough permissions"}
RESPONSE_FIELDS = {
    "id",
    "title",
    "description",
    "status",
    "priority",
    "due_date",
    "project_id",
    "author_id",
    "assignee_id",
    "created_at",
    "updated_at",
}

SHARED_HASH = hash_password("correct-horse-battery")
DUE = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


def task_url(project_id: int, task_id: int) -> str:
    return f"/projects/{project_id}/tasks/{task_id}"


@dataclass
class Team:
    owner: User
    admin: User
    member: User
    viewer: User
    outsider: User
    project: Project

    def user(self, role: str) -> User:
        return getattr(self, role)


@pytest.fixture
def make_user(create_user: Callable):
    async def _make(email: str, **kwargs) -> User:
        return await create_user(email, hashed_password=SHARED_HASH, **kwargs)

    return _make


@pytest.fixture
async def team(make_user: Callable, create_project: Callable) -> Team:
    owner = await make_user("owner@example.com")
    admin = await make_user("admin@example.com")
    member = await make_user("member@example.com")
    viewer = await make_user("viewer@example.com")
    outsider = await make_user("outsider@example.com")
    project = await create_project(
        owner,
        "Shared",
        members=[
            (admin, ProjectRole.ADMIN),
            (member, ProjectRole.MEMBER),
            (viewer, ProjectRole.VIEWER),
        ],
    )
    return Team(owner, admin, member, viewer, outsider, project)


async def add_task(
    session_factory: async_sessionmaker[AsyncSession],
    project: Project,
    author: User,
    title: str = "Original",
    *,
    description: str | None = "Original description",
    status: TaskStatus = TaskStatus.TODO,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: datetime | None = DUE,
    assignee_id: int | None = None,
) -> Task:
    async with session_factory() as session:
        task = Task(
            title=title,
            description=description,
            status=status,
            priority=priority,
            due_date=due_date,
            project_id=project.id,
            author_id=author.id,
            assignee_id=assignee_id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


async def stored_task(
    session_factory: async_sessionmaker[AsyncSession], task_id: int
) -> Task | None:
    async with session_factory() as session:
        return await session.get(Task, task_id)


async def history_rows(
    session_factory: async_sessionmaker[AsyncSession], task_id: int
) -> list[TaskStatusHistory]:
    async with session_factory() as session:
        result = await session.execute(
            select(TaskStatusHistory)
            .where(TaskStatusHistory.task_id == task_id)
            .order_by(TaskStatusHistory.id)
        )
        return list(result.scalars().all())


async def test_update_task(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await add_task(session_factory, team.project, team.owner)
    actor = team.member

    response = await client.patch(
        task_url(team.project.id, task.id),
        json={"title": "  Renamed  "},
        headers=auth_headers(actor),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["title"] == "Renamed"
    assert body["author_id"] == team.owner.id
    assert body["project_id"] == team.project.id
    assert "author" not in body
    assert "hashed_password" not in response.text
    assert team.owner.hashed_password not in response.text
    stored = await stored_task(session_factory, task.id)
    assert stored is not None and stored.title == "Renamed"
    assert stored.author_id == team.owner.id


async def test_viewer_cannot_update(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await add_task(session_factory, team.project, team.owner)

    response = await client.patch(
        task_url(team.project.id, task.id),
        json={"title": "Hacked"},
        headers=auth_headers(team.viewer),
    )

    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    stored = await stored_task(session_factory, task.id)
    assert stored is not None and stored.title == "Original"


async def test_status_writes_history(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await add_task(session_factory, team.project, team.owner)

    response = await client.patch(
        task_url(team.project.id, task.id),
        json={"status": "in_progress"},
        headers=auth_headers(team.member),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    rows = await history_rows(session_factory, task.id)
    assert len(rows) == 1
    assert rows[0].old_status == TaskStatus.TODO
    assert rows[0].new_status == TaskStatus.IN_PROGRESS
    assert rows[0].changed_by_id == team.member.id


