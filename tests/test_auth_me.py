from collections.abc import Callable

import pytest
from httpx import AsyncClient


URL = "/auth/me"
EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_me_ok(client: AsyncClient, create_user: Callable) -> None:
    user = await create_user(EMAIL, PASSWORD)
    login = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    token = login.json()["access_token"]

    response = await client.get(URL, headers=bearer(token))

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "email": EMAIL,
        "full_name": "Alice Smith",
        "is_active": True,
    }


@pytest.mark.anyio
async def test_me_no_token(client: AsyncClient) -> None:
    response = await client.get(URL)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


