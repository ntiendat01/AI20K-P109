"""HTTP contracts shared by authentication, chat, and approval routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """A user message for the procurement assistant."""

    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    """A response from the procurement assistant."""

    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")


class LoginRequest(BaseModel):
    """Credentials submitted to the session endpoint."""

    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class UserProfile(BaseModel):
    """The signed-in user's public identity."""

    id: str
    name: str
    email: str
    role: Literal["procurement", "manager"]


class LoginResponse(BaseModel):
    """Authentication result returned to the client."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserProfile


class ApprovePRRequest(BaseModel):
    """Manager approval payload."""

    selected_quotation_id: str | None = None
    manager_note: str | None = None


class RejectPRRequest(BaseModel):
    """Manager rejection payload."""

    rejection_reason: str = Field(..., min_length=3, max_length=500)
