import asyncio
import logging

from fastapi import APIRouter, HTTPException, status
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.core.tokens import create_access_token
from app.db.errors import is_unique_violation
from app.models import User
from app.schemas import Token, UserCreate, UserLogin, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_ALREADY_REGISTERED = "User with this email already exists"

# Имя из naming_convention, его сверяет тест.
USERS_EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "Пользователь с таким email уже зарегистрирован",
            "content": {
                "application/json": {"example": {"detail": EMAIL_ALREADY_REGISTERED}},
            },
        },
    },
)
async def register(payload: UserCreate, db: DbSession) -> User:
    result = await db.execute(select(User.id).where(User.email == payload.email))
    email_taken = result.scalar_one_or_none() is not None

    # Не держать соединение, пока считается argon2.
    await db.rollback()

    if email_taken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EMAIL_ALREADY_REGISTERED)

    hashed_password = await asyncio.to_thread(hash_password, payload.password)

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hashed_password,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # 409 только если это гонка по email.
        if not is_unique_violation(exc, USERS_EMAIL_UNIQUE_CONSTRAINT):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=EMAIL_ALREADY_REGISTERED,
        ) from None

    return user


INVALID_CREDENTIALS = "Incorrect email or password"


@router.post(
    "/login",
    response_model=Token,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Неверный email или пароль (или пользователь неактивен)",
            "content": {
                "application/json": {"example": {"detail": INVALID_CREDENTIALS}},
            },
        },
    },
)
async def login(payload: UserLogin, db: DbSession) -> Token:
    # Колонки, не объект: после rollback объект сессии уже не прочитать.
    result = await db.execute(
        select(User.id, User.hashed_password, User.is_active).where(User.email == payload.email)
    )
    user = result.one_or_none()

    await db.rollback()

    hashed_password = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    try:
        password_ok = await asyncio.to_thread(verify_password, payload.password, hashed_password)
    except UnknownHashError:
        logger.error(
            "Stored password hash of user id=%s has unsupported format",
            user.id if user is not None else None,
        )
        password_ok = False

    if user is None or not user.is_active or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Токен отсутствует, недействителен или просрочен",
        },
    },
)
async def read_current_user(current_user: CurrentUser) -> User:
    return current_user