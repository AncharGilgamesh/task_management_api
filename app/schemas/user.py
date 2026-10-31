from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: FullName
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        # До валидации EmailStr: "  User@Example.COM " -> "user@example.com".
        if isinstance(value, str):
            return value.strip().lower()
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
