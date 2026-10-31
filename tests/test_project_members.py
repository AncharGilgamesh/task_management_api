from collections.abc import Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models import Project, ProjectMember, User
from app.models.enums import ProjectRole

pytestmark = pytest.mark.anyio

RESPONSE_FIELDS = {"user_id", "email", "full_name", "role", "joined_at"}
FORBIDDEN = {"detail": "Not enough permissions"}
ALREADY_MEMBER = {"detail": "User is already a project member"}

SHARED_HASH = hash_password("correct-horse-battery")


def members_url(project_id: int, user_id: int | None = None) -> str:
    url = f"/projects/{project_id}/members"
    if user_id is not None:
        return f"{url}/{user_id}"
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


async def stored_member(
    session_factory: async_sessionmaker[AsyncSession],
    project_id: int,
    user_id: int,
) -> ProjectMember | None:
    async with session_factory() as session:
        return await session.get(ProjectMember, (project_id, user_id))


def assert_safe_member(body: dict, user: User, role: str) -> None:
    assert set(body) == RESPONSE_FIELDS
    assert body["user_id"] == user.id
    assert body["email"] == user.email
    assert body["full_name"] == user.full_name
    assert body["role"] == role
    assert body["joined_at"]
    assert "hashed_password" not in body
    assert user.hashed_password not in str(body)
    assert "$argon2" not in str(body)


async def test_owner_adds_member(
    client: AsyncClient,
    make_user: Callable,
    create_project: Callable,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    role = "member"
    owner = await make_user("owner@example.com")
    target = await make_user(f"{role}@example.com")
    project = await create_project(owner, "Owned")

    response = await client.post(
        members_url(project.id),
        json={"user_id": target.id, "role": role},
        headers=auth_headers(owner),
    )

    assert response.status_code == 201
    assert_safe_member(response.json(), target, role)
    assert target.hashed_password not in response.text
    stored = await stored_member(session_factory, project.id, target.id)
    assert stored is not None and stored.role == ProjectRole(role)
    visible = await client.get(f"/projects/{project.id}", headers=auth_headers(target))
    assert visible.status_code == 200


async def test_duplicate_member(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await client.post(
        members_url(team.project.id),
        json={"user_id": team.viewer.id, "role": "member"},
        headers=auth_headers(team.owner),
    )

    assert response.status_code == 409
    assert response.json() == ALREADY_MEMBER
    stored = await stored_member(session_factory, team.project.id, team.viewer.id)
    assert stored is not None and stored.role == ProjectRole.VIEWER


async def test_member_cannot_add(
    client: AsyncClient,
    team: Team,
    make_user: Callable,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    role = "member"
    target = await make_user(f"target-{role}@example.com")

    response = await client.post(
        members_url(team.project.id),
        json={"user_id": target.id, "role": "viewer"},
        headers=auth_headers(team.member),
    )

    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    assert await stored_member(session_factory, team.project.id, target.id) is None


async def test_owner_removes_member(
    client: AsyncClient,
    team: Team,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    target = team.member

    response = await client.delete(members_url(team.project.id, target.id), headers=auth_headers(team.owner))

    assert response.status_code == 204
    assert response.content == b""
    assert await stored_member(session_factory, team.project.id, target.id) is None


async def test_admin_cannot_remove_admin(
    client: AsyncClient,
    team: Team,
    make_user: Callable,
    create_project: Callable,
    auth_headers: Callable,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    other_admin = await make_user("admin2@example.com")
    project = await create_project(
        team.owner,
        "Two admins",
        members=[(team.admin, ProjectRole.ADMIN), (other_admin, ProjectRole.ADMIN)],
    )

    response = await client.delete(members_url(project.id, other_admin.id), headers=auth_headers(team.admin))

    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    assert await stored_member(session_factory, project.id, other_admin.id) is not None


