from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, Task, TaskStatusHistory, User
from app.models.enums import ProjectRole, TaskStatus

pytestmark = pytest.mark.anyio

HISTORY_FIELDS = {
    "id",
    "task_id",
    "old_status",
    "new_status",
    "changed_by_id",
    "changed_at",
}

SHARED_HASH = hash_password("correct-horse-battery")
T_EARLY = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def history_url(project_id: int, task_id: int) -> str:
    return f"/projects/{project_id}/tasks/{task_id}/history"


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


async def add_history_row(
    session_factory: async_sessionmaker[AsyncSession],
    task: Task,
    *,
    old_status: TaskStatus | None,
    new_status: TaskStatus,
    changed_by_id: int | None,
    changed_at: datetime,
) -> TaskStatusHistory:
    async with session_factory() as session:
        row = TaskStatusHistory(
            task_id=task.id,
            old_status=old_status,
            new_status=new_status,
            changed_by_id=changed_by_id,
            changed_at=changed_at,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


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


def history_signature(rows: list[TaskStatusHistory]) -> list[tuple]:
    return [
        (row.id, row.old_status, row.new_status, row.changed_by_id, row.changed_at)
        for row in rows
    ]


async def test_read_history(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    created = await client.post(
        f"/projects/{team.project.id}/tasks",
        json={"title": "Tracked"},
        headers=auth_headers(team.owner),
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    patched = await client.patch(
        f"/projects/{team.project.id}/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=auth_headers(team.member),
    )
    assert patched.status_code == 200

    other = await add_task(session_factory, team.project, team.owner, "Other")
    other_row = await add_history_row(
        session_factory,
        other,
        old_status=TaskStatus.TODO,
        new_status=TaskStatus.DONE,
        changed_by_id=team.admin.id,
        changed_at=T_EARLY,
    )
    before_task = await stored_task(session_factory, task_id)
    before_history = await history_rows(session_factory, task_id)
    assert before_task is not None

    response = await client.get(
        history_url(team.project.id, task_id),
        headers=auth_headers(team.member),
    )

    assert response.status_code == 200
    body = response.json()
    assert [set(item) for item in body] == [HISTORY_FIELDS, HISTORY_FIELDS]
    assert [(item["old_status"], item["new_status"]) for item in body] == [
        (None, "todo"),
        ("todo", "in_progress"),
    ]
    assert [item["id"] for item in body] == [row.id for row in before_history]
    assert [item["task_id"] for item in body] == [task_id, task_id]
    assert [item["changed_by_id"] for item in body] == [team.owner.id, team.member.id]
    assert datetime.fromisoformat(body[0]["changed_at"]) <= datetime.fromisoformat(body[1]["changed_at"])
    assert other_row.id not in {item["id"] for item in body}
    assert all("changed_by" not in item for item in body)
    assert "hashed_password" not in response.text
    assert team.owner.hashed_password not in response.text
    assert "owner@example.com" not in response.text
    assert "member@example.com" not in response.text

    after_task = await stored_task(session_factory, task_id)
    assert after_task is not None
    assert after_task.title == before_task.title
    assert after_task.status == before_task.status
    assert after_task.updated_at == before_task.updated_at
    assert history_signature(await history_rows(session_factory, task_id)) == history_signature(before_history)


