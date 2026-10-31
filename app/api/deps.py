from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tokens import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models import User

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Логин принимает JSON, форма Swagger с username/password к нему не подходит.
bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description=(
        "Access token из POST /auth/login. Вставьте сам JWT, без префикса Bearer: "
        "Swagger добавит его сам."
    ),
)


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    if credentials is None or not credentials.credentials:
        raise credentials_exception()
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise credentials_exception() from None

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
