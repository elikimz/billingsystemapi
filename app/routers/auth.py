import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_async_db
from app.models.models import User, AdminUser, UserStatus
from app.schemas.schemas import UserRegister, UserLogin, AdminLogin, TokenResponse
from app.core.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register_user(payload: UserRegister, db: AsyncSession = Depends(get_async_db)):
    """Register a new portal user."""
    result = await db.execute(select(User).where(User.phone_number == payload.phone_number))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Phone number already registered")

    user = User(
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        email=payload.email,
        password_hash=hash_password(payload.password) if payload.password else None,
        status=UserStatus.ACTIVE,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "type": "user"})
    logger.info(f"New user registered: {user.phone_number}")
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        full_name=user.full_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin, db: AsyncSession = Depends(get_async_db)):
    """Login a portal user."""
    result = await db.execute(select(User).where(User.phone_number == payload.phone_number))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid phone number or password")

    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="Account suspended")

    token = create_access_token({"sub": str(user.id), "type": "user"})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        full_name=user.full_name,
    )


@router.post("/admin/login", response_model=TokenResponse)
async def login_admin(payload: AdminLogin, db: AsyncSession = Depends(get_async_db)):
    """Login an admin user."""
    result = await db.execute(select(AdminUser).where(AdminUser.email == payload.email))
    admin = result.scalar_one_or_none()

    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not admin.is_active:
        raise HTTPException(status_code=403, detail="Admin account inactive")

    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    logger.info(f"Admin login: {admin.email}")
    return TokenResponse(
        access_token=token,
        user_id=str(admin.id),
        full_name=admin.full_name,
        role=admin.role.value,
    )
