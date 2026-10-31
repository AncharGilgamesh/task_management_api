import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.db.session import engine, get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Task Management API",
    description="REST API для управления проектами и задачами.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Welcome to Task Management API"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def database_health(db: DbSession) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))

    except (SQLAlchemyError, OSError):
        logger.exception("Database health check failed")

        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from None

    return {
        "status": "ok",
        "database": "ok",
    }