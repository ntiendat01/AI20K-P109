import logging
from typing import Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infrastructure.auth import DemoUser, get_session

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> DemoUser:
    if credentials is None:
        logger.warning("Authentication required", extra={"event": "authentication_required"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bạn cần đăng nhập để tiếp tục.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_session(credentials.credentials).user


def require_role(*roles: Literal["procurement", "manager"]):
    def dependency(user: DemoUser = Depends(get_current_user)) -> DemoUser:
        if user.role not in roles:
            logger.warning(
                "Authorization denied",
                extra={
                    "event": "authorization_denied",
                    "actor_id": user.id,
                    "actor_role": user.role,
                    "required_roles": roles,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền truy cập chức năng này.",
            )
        return user

    return dependency
