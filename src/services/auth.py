"""Dịch vụ xác thực tối giản cho demo MVP.

Trong giai đoạn MVP, người dùng demo được khai báo cố định để đội có thể kiểm
thử luồng phân quyền mà chưa cần cơ sở dữ liệu. Token chỉ được giữ trong bộ nhớ
tiến trình, vì vậy không dùng cho môi trường production.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import HTTPException, status

SESSION_DURATION_MINUTES = 30
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoUser:
    id: str
    name: str
    email: str
    role: str
    password: str


DEMO_USERS = (
    DemoUser(
        id="user-procurement-01",
        name="Nguyễn Minh Anh",
        email="purchasing@vinuni.edu.vn",
        role="procurement",
        password="Purchase123!",
    ),
    DemoUser(
        id="user-manager-01",
        name="Trần Quang Huy",
        email="manager@vinuni.edu.vn",
        role="manager",
        password="Manager123!",
    ),
)


@dataclass
class Session:
    user: DemoUser
    expires_at: datetime


_sessions: dict[str, Session] = {}


def authenticate(email: str, password: str) -> DemoUser | None:
    """Trả về user khi thông tin đăng nhập demo hợp lệ."""
    normalized_email = email.strip().lower()
    for user in DEMO_USERS:
        if user.email == normalized_email and user.password == password:
            return user
    logger.warning("Authentication failed", extra={"event": "authentication_failed"})
    return None


def create_session(user: DemoUser) -> tuple[str, datetime]:
    token = token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=SESSION_DURATION_MINUTES)
    _sessions[token] = Session(user=user, expires_at=expires_at)
    logger.info(
        "Authentication succeeded",
        extra={"event": "authentication_succeeded", "actor_id": user.id, "actor_role": user.role},
    )
    return token, expires_at


def get_session(token: str) -> Session:
    session = _sessions.get(token)
    if session is None:
        logger.warning("Session token rejected", extra={"event": "invalid_session_token"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if session.expires_at <= datetime.now(UTC):
        _sessions.pop(token, None)
        logger.warning(
            "Expired session rejected",
            extra={"event": "expired_session_token", "actor_id": session.user.id, "actor_role": session.user.role},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return session


def revoke_session(token: str) -> None:
    session = _sessions.pop(token, None)
    if session is not None:
        logger.info(
            "Session revoked",
            extra={"event": "session_revoked", "actor_id": session.user.id, "actor_role": session.user.role},
        )
