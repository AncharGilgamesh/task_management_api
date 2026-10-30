from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_session() -> Iterator[AsyncMock]:
    session = AsyncMock()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.clear()


def test_health_db_ok(
    mock_session: AsyncMock,
) -> None:
    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    mock_session.execute.assert_awaited_once()


def test_health_db_down(
    mock_session: AsyncMock,
) -> None:
    mock_session.execute.side_effect = SQLAlchemyError("connection refused: secret")

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "secret" not in response.text
