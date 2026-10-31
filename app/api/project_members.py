from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.db.errors import is_unique_violation
from app.models import Project, ProjectMember, User
from app.models.enums import ProjectRole
from app.schemas import ProjectMemberCreate, ProjectMemberResponse, ProjectMemberUpdate
from app.services.project_access import (
    NOT_ENOUGH_PERMISSIONS,
    PROJECT_NOT_FOUND,
    AccessLevel,
    Permission,
    actor_level_for_membership_changes,
    get_project_or_error,
    require_outranks,
    resolve_access_level,
)

router = APIRouter(prefix="/projects/{project_id}/members", tags=["project-members"])

MAX_INT32 = 2_147_483_647
ProjectId = Annotated[int, Path(ge=1, le=MAX_INT32)]
UserId = Annotated[int, Path(ge=1, le=MAX_INT32)]

PROJECT_MEMBERS_PK = "pk_project_members"

USER_NOT_FOUND = "User not found"
USER_INACTIVE = "User is inactive"
OWNER_CANNOT_BE_MEMBER = "Project owner cannot be a member"
ALREADY_MEMBER = "User is already a project member"
MEMBER_NOT_FOUND = "Project member not found"

_UNAUTHORIZED = {"description": "Токен отсутствует, недействителен или просрочен"}
_PROJECT_NOT_FOUND = {
    "description": "Проект не найден или у пользователя нет к нему доступа",
    "content": {"application/json": {"example": {"detail": PROJECT_NOT_FOUND}}},
}
_FORBIDDEN = {
    "description": "Доступ к проекту есть, но прав на управление участниками недостаточно",
    "content": {"application/json": {"example": {"detail": NOT_ENOUGH_PERMISSIONS}}},
}
_MEMBER_NOT_FOUND = {
    "description": "В проекте нет такого участника",
    "content": {"application/json": {"example": {"detail": MEMBER_NOT_FOUND}}},
}


def _role_level(project: Project, user: User, role: ProjectRole) -> AccessLevel:
    """Уровень роли. Владельца сюда передавать нельзя: у него уровень всегда OWNER."""
    level = resolve_access_level(project, user, role)
    if level is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_ENOUGH_PERMISSIONS)
    return level


def _response(
    *,
    user_id: int,
    email: str,
    full_name: str,
    role: ProjectRole,
    joined_at: datetime,
) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        user_id=user_id,
        email=email,
        full_name=full_name,
        role=role,
        joined_at=joined_at,
    )


@router.post(
    "",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: _FORBIDDEN,
        status.HTTP_404_NOT_FOUND: _PROJECT_NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": "Пользователя нельзя добавить в проект"},
    },
)
async def add_project_member(
    project_id: ProjectId,
    payload: ProjectMemberCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectMemberResponse:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.UPDATE)
    actor_level = actor_level_for_membership_changes(project, current_user)

    user = await db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=USER_INACTIVE)
    if user.id == project.owner_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OWNER_CANNOT_BE_MEMBER)

    existing = await db.get(ProjectMember, (project.id, user.id))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_MEMBER)

    require_outranks(actor_level, _role_level(project, user, payload.role))

    member = ProjectMember(project_id=project.id, user_id=user.id, role=payload.role)
    db.add(member)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if not is_unique_violation(exc, PROJECT_MEMBERS_PK):
            raise
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_MEMBER) from None

    await db.refresh(member)
    return _response(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.joined_at,
    )


@router.get(
    "",
    response_model=list[ProjectMemberResponse],
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND: _PROJECT_NOT_FOUND,
    },
)
async def list_project_members(
    project_id: ProjectId,
    current_user: CurrentUser,
    db: DbSession,
) -> list[ProjectMemberResponse]:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.READ)
    result = await db.execute(
        select(
            ProjectMember.user_id,
            User.email,
            User.full_name,
            ProjectMember.role,
            ProjectMember.joined_at,
        )
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id)
        .order_by(ProjectMember.user_id)
    )
    return [
        _response(
            user_id=row.user_id,
            email=row.email,
            full_name=row.full_name,
            role=row.role,
            joined_at=row.joined_at,
        )
        for row in result.all()
    ]


async def _member_for_change(
    db: DbSession,
    project: Project,
    user_id: int,
) -> tuple[ProjectMember, User]:
    result = await db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id, ProjectMember.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MEMBER_NOT_FOUND)
    return row


@router.patch(
    "/{user_id}",
    response_model=ProjectMemberResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: _FORBIDDEN,
        status.HTTP_404_NOT_FOUND: _MEMBER_NOT_FOUND,
    },
)
async def update_project_member(
    project_id: ProjectId,
    user_id: UserId,
    payload: ProjectMemberUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectMemberResponse:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.UPDATE)
    actor_level = actor_level_for_membership_changes(project, current_user)
    member, user = await _member_for_change(db, project, user_id)

    require_outranks(
        actor_level,
        _role_level(project, user, member.role),
        _role_level(project, user, payload.role),
    )
    member.role = payload.role
    await db.commit()
    return _response(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=member.role,
        joined_at=member.joined_at,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: _FORBIDDEN,
        status.HTTP_404_NOT_FOUND: _MEMBER_NOT_FOUND,
    },
)
async def delete_project_member(
    project_id: ProjectId,
    user_id: UserId,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    project = await get_project_or_error(db, project_id, current_user, required=Permission.UPDATE)
    actor_level = actor_level_for_membership_changes(project, current_user)
    member, user = await _member_for_change(db, project, user_id)

    require_outranks(actor_level, _role_level(project, user, member.role))
    await db.delete(member)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
