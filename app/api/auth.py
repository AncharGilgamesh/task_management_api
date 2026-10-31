import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

EMAIL_ALREADY_REGISTERED = "User with this email already exists"


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: UserCreate, db: DbSession) -> User:
    existing = await db.execute(select(User.id).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
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
    except IntegrityError:
        # Гонка: другой запрос успел зарегистрировать тот же email между проверкой и вставкой.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=EMAIL_ALREADY_REGISTERED,
        ) from None

    return user
