from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectRole

UserId = Annotated[int, Field(ge=1, le=2_147_483_647)]


class ProjectMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UserId
    role: ProjectRole


class ProjectMemberUpdate(BaseModel):
    """Новая роль. Поле обязательное."""

    model_config = ConfigDict(extra="forbid")

    role: ProjectRole


class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    email: str
    full_name: str
    role: ProjectRole
    joined_at: datetime
