from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


def _empty_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


ProjectDescription = Annotated[
    Annotated[str, StringConstraints(max_length=5000)] | None,
    BeforeValidator(_empty_to_none),
]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: ProjectDescription = None


class ProjectUpdate(BaseModel):
    """Меняются только переданные поля."""

    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
    description: ProjectDescription = None

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime
