from collections.abc import Callable

import jwt
import pytest
from httpx import AsyncClient, Response

from app.core.config import settings

pytestmark = pytest.mark.anyio

URL = "/auth/login"
EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery"
INVALID_CREDENTIALS = {"detail": "Incorrect email or password"}


def credentials(**overrides: str) -> dict[str, str]:
    return {"email": EMAIL, "password": PASSWORD, **overrides}


def assert_unauthorized(response: Response) -> None:
    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS
    assert response.headers["www-authenticate"] == "Bearer"


async def test_login_ok(client: AsyncClient, create_user: Callable) -> None:
    user = await create_user(EMAIL, PASSWORD)

    response = await client.post(URL, json=credentials())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    claims = jwt.decode(
        body["access_token"], settings.secret_key.get_secret_value(), algorithms=["HS256"]
    )
    assert claims["sub"] == str(user.id)
    assert set(claims) == {"sub", "iat", "exp", "jti"}
    assert claims["exp"] - claims["iat"] == body["expires_in"]


async def test_login_wrong_password(client: AsyncClient, create_user: Callable) -> None:
    await create_user(EMAIL, PASSWORD)

    response = await client.post(URL, json=credentials(password="wrong-password"))

    assert_unauthorized(response)


