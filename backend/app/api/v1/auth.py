from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.schemas import LoginRequest, LoginResponse
from app.core.logging import get_logger
from app.core.security import create_access_token, verify_password
from app.db.models.user import User
from app.db.session import get_db
logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    if user is None:
        logger.warning(f"Login attempt with non-existent email: {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not verify_password(credentials.password, user.password_hash):
        logger.warning(f"Failed login attempt for user: {credentials.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    logger.info(f"Successful login for user: {credentials.email}")
    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        email=user.email,
        role=user.role,
    )
