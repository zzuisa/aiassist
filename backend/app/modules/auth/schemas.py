"""Auth request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = {"extra": "forbid"}
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    timezone: str
    locale: str
    notification_preferences: dict = {}


class LoginResponse(BaseModel):
    user: UserOut
    csrf_token: str
