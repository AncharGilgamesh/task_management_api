from enum import IntEnum, StrEnum

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectMember, User
from app.models.enums import ProjectRole

PROJECT_NOT_FOUND = "Project not found"
NOT_ENOUGH_PERMISSIONS = "Not enough permissions"


class AccessLevel(IntEnum):

    VIEWER = 1
    MEMBER = 2
    ADMIN = 3
    OWNER = 4


class Permission(StrEnum):
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


REQUIRED_LEVEL: dict[Permission, AccessLevel] = {
    Permission.READ: AccessLevel.VIEWER,
    Permission.UPDATE: AccessLevel.ADMIN,
    Permission.DELETE: AccessLevel.OWNER,
}

_MEMBER_LEVEL: dict[ProjectRole, AccessLevel] = {
    ProjectRole.VIEWER: AccessLevel.VIEWER,
    ProjectRole.MEMBER: AccessLevel.MEMBER,
    ProjectRole.ADMIN: AccessLevel.ADMIN,
}


def resolve_access_level(
    project: Project,
    user: User,
    member_role: ProjectRole | None,
) -> AccessLevel | None:
    if project.owner_id == user.id:
        return AccessLevel.OWNER
    if member_role is None:
        return None
    return _MEMBER_LEVEL[member_role]


async def get_project_or_error(
    db: AsyncSession,
    project_id: int,
    user: User,
    *,
    required: Permission,
) -> Project:

    result = await db.execute(
        select(Project, ProjectMember.role)
        .outerjoin(
            ProjectMember,
            and_(ProjectMember.project_id == Project.id, ProjectMember.user_id == user.id),
        )
        .where(Project.id == project_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PROJECT_NOT_FOUND)

    project, member_role = row
    level = resolve_access_level(project, user, member_role)
    if level is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=PROJECT_NOT_FOUND)
    if level < REQUIRED_LEVEL[required]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_ENOUGH_PERMISSIONS)
    return project
