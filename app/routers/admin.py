import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from uuid import UUID
from decimal import Decimal
from app.database.database import get_async_db
from app.models.models import (
    User, AdminUser, Plan, Subscription, Payment, Voucher,
    SMSLog, AuditLog, SystemSetting, Router,
    SubscriptionStatus, PaymentStatus, AdminRole
)
from app.schemas.schemas import (
    AdminCreate, AdminOut, UserOut, DashboardStats,
    SettingUpdate, SettingOut, AuditLogOut, SMSLogOut,
    RouterCreate, RouterOut
)
from app.core.deps import get_current_admin
from app.core.security import hash_password

router = APIRouter(prefix="/admin", tags=["Admin"])
logger = logging.getLogger(__name__)


# ========================
# DASHBOARD
# ========================

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active_subs = (await db.execute(
        select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE)
    )).scalar() or 0
    total_revenue = (await db.execute(
        select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.SUCCESS)
    )).scalar() or Decimal("0")
    total_payments = (await db.execute(select(func.count(Payment.id)))).scalar() or 0
    active_plans = (await db.execute(
        select(func.count(Plan.id)).where(Plan.is_active == True)
    )).scalar() or 0
    total_vouchers = (await db.execute(select(func.count(Voucher.id)))).scalar() or 0
    redeemed_vouchers = (await db.execute(
        select(func.count(Voucher.id)).where(Voucher.status == "redeemed")
    )).scalar() or 0

    return DashboardStats(
        total_users=total_users,
        active_subscriptions=active_subs,
        total_revenue=total_revenue,
        total_payments=total_payments,
        active_plans=active_plans,
        total_vouchers=total_vouchers,
        redeemed_vouchers=redeemed_vouchers,
    )


# ========================
# ADMIN USERS
# ========================

@router.post("/admins", response_model=AdminOut, status_code=201)
async def create_admin(
    payload: AdminCreate,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    if admin.role != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super admins can create admin accounts")

    existing = await db.execute(select(AdminUser).where(AdminUser.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_admin = AdminUser(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=AdminRole(payload.role),
        is_active=True,
    )
    db.add(new_admin)
    db.add(AuditLog(
        admin_user_id=admin.id,
        action="CREATE",
        entity_type="AdminUser",
        details=f"Created admin: {payload.email}",
    ))
    await db.commit()
    await db.refresh(new_admin)
    return new_admin


@router.get("/admins", response_model=List[AdminOut])
async def list_admins(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(AdminUser).order_by(AdminUser.created_at.desc()))
    return result.scalars().all()


# ========================
# USERS
# ========================

@router.get("/users", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users/{user_id}/suspend", status_code=200)
async def suspend_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    from app.models.models import UserStatus
    user.status = UserStatus.SUSPENDED
    db.add(AuditLog(
        admin_user_id=admin.id,
        action="SUSPEND",
        entity_type="User",
        entity_id=str(user_id),
        details=f"Suspended user: {user.phone_number}",
    ))
    await db.commit()
    return {"message": "User suspended"}


# ========================
# SYSTEM SETTINGS
# ========================

@router.get("/settings", response_model=List[SettingOut])
async def list_settings(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.is_active == True))
    return result.scalars().all()


@router.put("/settings/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    payload: SettingUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    setting.value = payload.value
    db.add(AuditLog(
        admin_user_id=admin.id,
        action="UPDATE",
        entity_type="SystemSetting",
        entity_id=key,
        details=f"Updated setting: {key}",
    ))
    await db.commit()
    await db.refresh(setting)
    return setting


# ========================
# AUDIT LOGS
# ========================

@router.get("/audit-logs", response_model=List[AuditLogOut])
async def list_audit_logs(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500))
    return result.scalars().all()


# ========================
# SMS LOGS
# ========================

@router.get("/sms-logs", response_model=List[SMSLogOut])
async def list_sms_logs(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(SMSLog).order_by(SMSLog.created_at.desc()).limit(500))
    return result.scalars().all()


# ========================
# ROUTERS
# ========================

@router.get("/routers", response_model=List[RouterOut])
async def list_routers(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Router).order_by(Router.created_at.desc()))
    return result.scalars().all()


@router.post("/routers", response_model=RouterOut, status_code=201)
async def create_router(
    payload: RouterCreate,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    from app.models.models import RouterStatus
    router_obj = Router(
        name=payload.name,
        ip_address=payload.ip_address,
        location=payload.location,
        username=payload.username,
        password_encrypted=payload.password_encrypted,
        api_port=payload.api_port,
        status=RouterStatus.ACTIVE,
    )
    db.add(router_obj)
    await db.commit()
    await db.refresh(router_obj)
    return router_obj
