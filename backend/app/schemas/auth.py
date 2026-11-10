"""Authentication and profile contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.types import DisplayName, NewPassword, TimeZoneName


class RegisterRequest(BaseModel):
    email: EmailStr
    password: NewPassword
    display_name: DisplayName
    timezone: TimeZoneName


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    timezone: str
    created_at: datetime


class UserUpdate(BaseModel):
    display_name: DisplayName | None = None
    timezone: TimeZoneName | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105  # OAuth token type, not a credential.
    expires_in: int
    user: UserRead
