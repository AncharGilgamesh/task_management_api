import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.errors import is_unique_violation
from app.db.session import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

EMAIL_ALREADY_REGISTERED = "User with this email already exists"

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
        if not is_unique_violation(exc, USERS_EMAIL_UNIQUE_CONSTRAINT):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=EMAIL_ALREADY_REGISTERED,
        ) from None

    return user
