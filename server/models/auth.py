from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


UserRole = Literal["owner", "admin", "agent", "customer"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class LogoutRequest(RefreshRequest):
    pass


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    workspace_id: UUID
    role: UserRole


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
