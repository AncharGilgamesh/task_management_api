import os
from collections.abc import AsyncIterator, Sequence

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

TEST_SECRET_KEY = "test-only-secret-key-not-for-production-0123456789"
os.environ["SECRET_KEY"] = TEST_SECRET_KEY
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.core.tokens import create_access_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Project, ProjectMember, User  # noqa: E402
from app.models.enums import ProjectRole  # noqa: E402


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Своя SQLite в памяти на тест."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(bind=engine, expire_on_commit=False)

    await engine.dispose()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
def create_user(session_factory: async_sessionmaker[AsyncSession]):
    """Пользователь сразу в базе, без API."""

    async def _create(
        email: str = "alice@example.com",
        password: str = "correct-horse-battery",
        *,
        is_active: bool = True,
        hashed_password: str | None = None,
    ) -> User:
        async with session_factory() as session:
            user = User(
                email=email,
                full_name="Alice Smith",
                hashed_password=hashed_password or hash_password(password),
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            return user

    return _create

@pytest.fixture
def auth_headers():
    """Заголовок Authorization для пользователя."""

    def _headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user.id)}"}

    return _headers


@pytest.fixture
def create_project(session_factory: async_sessionmaker[AsyncSession]):
    """Проект и участники сразу в базе."""

    async def _create(
        owner: User,
        name: str = "Project",
        description: str | None = None,
        *,
        members: Sequence[tuple[User, ProjectRole]] = (),
    ) -> Project:
        async with session_factory() as session:
            project = Project(name=name, description=description, owner_id=owner.id)
            session.add(project)
            await session.flush()
            for user, role in members:
                session.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
            await session.commit()
            return project

    return _create