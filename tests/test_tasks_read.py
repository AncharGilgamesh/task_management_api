from collections.abc import Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, Task, User
from app.models.enums import ProjectRole, TaskPriority, TaskStatus

pytestmark = pytest.mark.anyio

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


def tasks_url(project_id: int, task_id: int | None = None) -> str:
    url = f"/projects/{project_id}/tasks"
    if task_id is not None:
        return f"{url}/{task_id}"
    return url


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
    title: str,
    *,
    status: TaskStatus = TaskStatus.TODO,
    priority: TaskPriority = TaskPriority.MEDIUM,
    assignee_id: int | None = None,
) -> Task:
    async with session_factory() as session:
        task = Task(
            title=title,
            status=status,
            priority=priority,
            project_id=project.id,
            author_id=author.id,
            assignee_id=assignee_id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


def assert_task_body(body: dict, task: Task) -> None:
    assert set(body) == RESPONSE_FIELDS
    assert body["id"] == task.id
    assert body["title"] == task.title
    assert body["status"] == task.status
    assert body["priority"] == task.priority
    assert body["project_id"] == task.project_id
    assert body["author_id"] == task.author_id
    assert body["assignee_id"] == task.assignee_id
    assert "author" not in body
    assert "assignee" not in body
    assert "hashed_password" not in body


async def test_list_and_get_tasks(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await add_task(session_factory, team.project, team.owner, "Visible")

    listed = await client.get(tasks_url(team.project.id), headers=auth_headers(team.member))
    single = await client.get(tasks_url(team.project.id, task.id), headers=auth_headers(team.member))

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [task.id]
    assert_task_body(listed.json()[0], task)
    assert team.owner.hashed_password not in listed.text
    assert single.status_code == 200
    assert_task_body(single.json(), task)
    assert team.owner.hashed_password not in single.text
    assert "$argon2" not in single.text


async def test_filter_by_status(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    todo = await add_task(session_factory, team.project, team.owner, "Todo")
    started = await add_task(
        session_factory, team.project, team.owner, "Started", status=TaskStatus.IN_PROGRESS
    )
    await add_task(session_factory, team.project, team.owner, "Done", status=TaskStatus.DONE)

    response = await client.get(
        tasks_url(team.project.id),
        params={"status": "in_progress"},
        headers=auth_headers(team.member),
    )

    assert [item["id"] for item in response.json()] == [started.id]
    assert todo.id not in {item["id"] for item in response.json()}


