from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.models import Project, ProjectMember
from app.schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_access import (
    NOT_ENOUGH_PERMISSIONS,
    PROJECT_NOT_FOUND,
    Permission,
    get_project_or_error,
)

router = APIRouter(prefix="/projects", tags=["projects"])

# Больше int32 asyncpg не принимает.
MAX_INT32 = 2_147_483_647
ProjectId = Annotated[int, Path(ge=1, le=MAX_INT32)]

_UNAUTHORIZED = {
    "description": "Токен отсутствует, недействителен или просрочен",
}
_NOT_FOUND = {
    "description": "Проект не найден или у пользователя нет к нему доступа",
    "content": {"application/json": {"example": {"detail": PROJECT_NOT_FOUND}}},
}
_FORBIDDEN = {
    "description": "Доступ к проекту есть, но прав на это действие недостаточно",
    "content": {"application/json": {"example": {"detail": NOT_ENOUGH_PERMISSIONS}}},
}


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
async def create_project(payload: ProjectCreate, current_user: CurrentUser, db: DbSession) -> Project:
    project = Project(
        name=payload.name,
        description=payload.description,
        owner_id=current_user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get(
    "",
    response_model=list[ProjectResponse],
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED},
)
async def list_projects(
    current_user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Project]:
    member_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)
    result = await db.execute(
        select(Project)
        .where(or_(Project.owner_id == current_user.id, Project.id.in_(member_project_ids)))
        .order_by(Project.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND,
    },
)
async def get_project(project_id: ProjectId, current_user: CurrentUser, db: DbSession) -> Project:
    return await get_project_or_error(db, project_id, current_user, required=Permission.READ)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: _FORBIDDEN,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND,
    },
)
async def update_project(
    project_id: ProjectId,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> Project:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.UPDATE)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: _FORBIDDEN,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND,
    },
)
async def delete_project(project_id: ProjectId, current_user: CurrentUser, db: DbSession) -> Response:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.DELETE)

    await db.delete(project)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
