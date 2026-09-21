"""Authentication dependencies for FastAPI routes."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key import verify_api_key
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.models.device import Device
from app.db.models.user import User
from app.db.session import get_db

logger = get_logger(__name__)

# Security schemes
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    Args:
        credentials: Bearer token from Authorization header
        db: Database session

    Returns:
        Authenticated user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_device(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    Dependency to authenticate device via API key.

    Args:
        credentials: Bearer token (device API key) from Authorization header
        db: Database session

    Returns:
        Authenticated device

    Raises:
        HTTPException: If API key is invalid
    """
    api_key = credentials.credentials

    # Fetch all devices (in production, optimize with indexed lookup)
    result = await db.execute(select(Device))
    devices = result.scalars().all()

    for device in devices:
        if verify_api_key(api_key, device.api_key_hash):
            return device

    logger.warning(f"Invalid device API key attempted")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*allowed_roles: str):
    """
    Dependency factory to require specific user roles.

    Usage:
        @router.patch("/detections/{id}")
        async def update_detection(
            user: User = Depends(require_role("admin", "operator"))
        ):
            ...

    Args:
        allowed_roles: Roles that are allowed to access the endpoint

    Returns:
        Dependency function that checks user role
    """

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_checker


# Convenient aliases for common role requirements
require_admin = require_role("admin")
require_operator_or_admin = require_role("operator", "admin")
require_any_user = get_current_user  # Any authenticated user
