from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, Task, TaskStatusHistory, User
from app.models.enums import ProjectRole, TaskPriority, TaskStatus

pytestmark = pytest.mark.anyio

PROJECT_NOT_FOUND = {"detail": "Project not found"}
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


def tasks_url(project_id: int) -> str:
    return f"/projects/{project_id}/tasks"


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


async def task_count(session_factory: async_sessionmaker[AsyncSession], project_id: int) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(Task).where(Task.project_id == project_id)
        )
        return result.scalar_one()


async def history_for(
    session_factory: async_sessionmaker[AsyncSession], task_id: int
) -> list[TaskStatusHistory]:
    async with session_factory() as session:
        result = await session.execute(
            select(TaskStatusHistory)
            .where(TaskStatusHistory.task_id == task_id)
            .order_by(TaskStatusHistory.id)
        )
        return list(result.scalars().all())


async def test_create_task(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    actor = team.member

    response = await client.post(
        tasks_url(team.project.id),
        json={
            "title": "  Fix login  ",
            "description": "  Details  ",
            "priority": "high",
            "due_date": DUE.isoformat(),
            "assignee_id": None,
        },
        headers=auth_headers(actor),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["title"] == "Fix login"
    assert body["description"] == "Details"
    assert body["status"] == TaskStatus.TODO
    assert body["priority"] == TaskPriority.HIGH
    assert body["project_id"] == team.project.id
    assert body["author_id"] == actor.id
    assert body["assignee_id"] is None
    assert body["created_at"] and body["updated_at"]
    assert "author" not in body
    assert "hashed_password" not in response.text
    assert actor.hashed_password not in response.text
    history = await history_for(session_factory, body["id"])
    assert len(history) == 1
    assert history[0].task_id == body["id"]
    assert history[0].old_status is None
    assert history[0].new_status is TaskStatus.TODO
    assert history[0].changed_by_id == actor.id
    assert history[0].changed_at is not None


async def test_viewer_cannot_create(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post(
        tasks_url(team.project.id),
        json={"title": "Secret"},
        headers=auth_headers(team.viewer),
    )

    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    assert await task_count(session_factory, team.project.id) == 0


async def test_outsider_gets_404(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    missing = await client.post(
        tasks_url(team.project.id + 1000),
        json={"title": "Ghost", "assignee_id": team.member.id},
        headers=auth_headers(team.owner),
    )
    foreign = await client.post(
        tasks_url(team.project.id),
        json={"title": "Ghost", "assignee_id": 2_147_483_647},
        headers=auth_headers(team.outsider),
    )

    assert missing.status_code == foreign.status_code == 404
    assert missing.json() == foreign.json() == PROJECT_NOT_FOUND
    assert "Assignee not found" not in foreign.text
    assert await task_count(session_factory, team.project.id) == 0


