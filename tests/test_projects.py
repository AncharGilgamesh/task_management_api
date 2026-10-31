from collections.abc import Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, ProjectMember, User
from app.models.enums import ProjectRole

URL = "/projects"
NOT_FOUND_BODY = {"detail": "Project not found"}
FORBIDDEN_BODY = {"detail": "Not enough permissions"}
RESPONSE_FIELDS = {"id", "name", "description", "owner_id", "created_at", "updated_at"}

# Argon2 дорогой: хеш считается один раз на весь модуль, а не на каждого пользователя в каждом тесте.
SHARED_HASH = hash_password("correct-horse-battery")


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
        "Secret project",
        "Original description",
        members=[
            (admin, ProjectRole.ADMIN),
            (member, ProjectRole.MEMBER),
            (viewer, ProjectRole.VIEWER),
        ],
    )
    return Team(owner, admin, member, viewer, outsider, project)


async def fetch_project(
    session_factory: async_sessionmaker[AsyncSession], project_id: int
) -> Project | None:
    async with session_factory() as session:
        return await session.get(Project, project_id)


async def count_rows(session_factory: async_sessionmaker[AsyncSession], model, **filters) -> int:
    async with session_factory() as session:
        query = select(func.count()).select_from(model)
        for column, value in filters.items():
            query = query.where(getattr(model, column) == value)
        return (await session.execute(query)).scalar_one()


@pytest.mark.anyio
async def test_create_project(
    client: AsyncClient,
    make_user: Callable,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await make_user("alice@example.com")

    response = await client.post(
        URL, json={"name": "My project", "description": "About it"}, headers=auth_headers(user)
    )

    assert response.status_code == 201
    data = response.json()
    assert set(data) == RESPONSE_FIELDS
    assert data["name"] == "My project"
    assert data["description"] == "About it"
    assert data["owner_id"] == user.id
    assert data["created_at"] and data["updated_at"]
    stored = await fetch_project(session_factory, data["id"])
    assert stored is not None
    assert stored.owner_id == user.id
    # Владелец определяется по owner_id: строка в project_members не создаётся.
    assert await count_rows(session_factory, ProjectMember, project_id=data["id"]) == 0


@pytest.mark.anyio
async def test_list_hides_foreign(
    client: AsyncClient, team: Team, auth_headers: Callable
) -> None:
    response = await client.get(URL, headers=auth_headers(team.outsider))

    assert response.status_code == 200
    assert response.json() == []
    assert "Secret project" not in response.text


@pytest.mark.anyio
async def test_get_foreign_project(
    client: AsyncClient, team: Team, auth_headers: Callable
) -> None:
    response = await client.get(f"{URL}/{team.project.id}", headers=auth_headers(team.outsider))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


@pytest.mark.anyio
async def test_patch_project(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.patch(
        f"{URL}/{team.project.id}",
        json={"name": "Renamed", "description": "New description"},
        headers=auth_headers(team.owner),
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == RESPONSE_FIELDS
    assert data["name"] == "Renamed"
    assert data["description"] == "New description"
    assert data["owner_id"] == team.owner.id
    stored = await fetch_project(session_factory, team.project.id)
    assert stored is not None
    assert (stored.name, stored.description, stored.owner_id) == ("Renamed", "New description", team.owner.id)


@pytest.mark.anyio
async def test_patch_project_forbidden(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.patch(
        f"{URL}/{team.project.id}", json={"name": "Hacked"}, headers=auth_headers(team.member)
    )

    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    stored = await fetch_project(session_factory, team.project.id)
    assert stored is not None and stored.name == "Secret project"


@pytest.mark.anyio
async def test_delete_project(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.delete(f"{URL}/{team.project.id}", headers=auth_headers(team.owner))

    assert response.status_code == 204
    assert response.content == b""
    assert await fetch_project(session_factory, team.project.id) is None
    follow_up = await client.get(f"{URL}/{team.project.id}", headers=auth_headers(team.owner))
    assert follow_up.status_code == 404


