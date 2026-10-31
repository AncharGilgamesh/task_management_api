import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import User

pytestmark = pytest.mark.anyio

URL = "/auth/register"
PASSWORD = "correct-horse-battery"


def make_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "email": "alice@example.com",
        "full_name": "Alice Smith",
        "password": PASSWORD,
    }
    payload.update(overrides)
    return payload


async def test_register_ok(client: AsyncClient) -> None:
    response = await client.post(URL, json=make_payload())

    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], int)
    assert body["email"] == "alice@example.com"
    assert body["full_name"] == "Alice Smith"
    assert body["is_active"] is True


async def test_register_duplicate_email(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await client.post(URL, json=make_payload())
    assert first.status_code == 201

    # Тот же email в другом регистре и с пробелами — тоже дубликат.
    second = await client.post(URL, json=make_payload(email=" ALICE@example.com "))

    assert second.status_code == 409
    assert second.json() == {"detail": "User with this email already exists"}
    async with session_factory() as session:
        count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    assert count == 1


async def test_register_short_password(client: AsyncClient) -> None:
    response = await client.post(URL, json=make_payload(password="short"))

    assert response.status_code == 422


