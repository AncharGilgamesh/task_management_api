from collections.abc import Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, Task, TaskStatusHistory, User
from app.models.enums import ProjectRole, TaskStatus

pytestmark = pytest.mark.anyio

FORBIDDEN = {"detail": "Not enough permissions"}

SHARED_HASH = hash_password("correct-horse-battery")


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
) -> Task:
    async with session_factory() as session:
        task = Task(
            title=title,
            status=TaskStatus.TODO,
            project_id=project.id,
            author_id=author.id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


async def add_history(
    session_factory: async_sessionmaker[AsyncSession],
    task: Task,
    changed_by: User,
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                TaskStatusHistory(
                    task_id=task.id,
                    old_status=None,
                    new_status=TaskStatus.TODO,
                    changed_by_id=changed_by.id,
                ),
                TaskStatusHistory(
                    task_id=task.id,
                    old_status=TaskStatus.TODO,
                    new_status=TaskStatus.IN_PROGRESS,
                    changed_by_id=changed_by.id,
                ),
            ]
        )
        await session.commit()


async def stored_task(
    session_factory: async_sessionmaker[AsyncSession], task_id: int
) -> Task | None:
    async with session_factory() as session:
        return await session.get(Task, task_id)


async def history_count(
    session_factory: async_sessionmaker[AsyncSession], task_id: int | None = None
) -> int:
    async with session_factory() as session:
        query = select(func.count()).select_from(TaskStatusHistory)
        if task_id is not None:
            query = query.where(TaskStatusHistory.task_id == task_id)
        return (await session.execute(query)).scalar_one()


async def test_delete_task(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await add_task(session_factory, team.project, team.member, "To delete")
    other = await add_task(session_factory, team.project, team.owner, "Keep")
    await add_history(session_factory, task, team.member)
    await add_history(session_factory, other, team.owner)

    response = await client.delete(
        task_url(team.project.id, task.id),
        headers=auth_headers(team.admin),
    )

    assert response.status_code == 204
    assert response.content == b""
    assert await stored_task(session_factory, task.id) is None
    assert await history_count(session_factory, task.id) == 0
    kept = await stored_task(session_factory, other.id)
    assert kept is not None and kept.title == "Keep"
    assert await history_count(session_factory, other.id) == 2


async def test_member_cannot_delete(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await add_task(session_factory, team.project, team.owner)
    await add_history(session_factory, task, team.owner)

    response = await client.delete(
        task_url(team.project.id, task.id),
        headers=auth_headers(team.member),
    )

    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    stored = await stored_task(session_factory, task.id)
    assert stored is not None and stored.title == "Original"
    assert await history_count(session_factory, task.id) == 2


