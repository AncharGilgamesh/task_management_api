from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


def _normalize_email(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


NormalizedEmail = Annotated[EmailStr, BeforeValidator(_normalize_email)]


class UserCreate(BaseModel):
    email: NormalizedEmail
    full_name: FullName
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
