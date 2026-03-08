import logging
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.database.database import get_async_db
from app.models.models import (
    Voucher, VoucherStatus, Plan, User, Subscription, Transaction,
    SubscriptionStatus, TransactionType, TransactionStatus, UserStatus
)
from app.schemas.schemas import VoucherGenerate, VoucherRedeem, VoucherOut
from app.core.deps import get_current_admin
from app.integrations.sms import send_sms, build_subscription_sms

router = APIRouter(prefix="/vouchers", tags=["Vouchers"])
logger = logging.getLogger(__name__)


def generate_voucher_code(prefix: str = "", length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(chars) for _ in range(length))
    return f"{prefix}-{code}" if prefix else code


@router.post("/generate", response_model=List[VoucherOut], status_code=201)
async def generate_vouchers(
    payload: VoucherGenerate,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    """Generate voucher codes for a plan (admin only)."""
    plan_result = await db.execute(select(Plan).where(Plan.id == payload.plan_id, Plan.is_active == True))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")

    vouchers = []
    for _ in range(payload.quantity):
        code = generate_voucher_code(prefix=payload.prefix or "")
        # Ensure uniqueness
        while True:
            existing = await db.execute(select(Voucher).where(Voucher.code == code))
            if not existing.scalar_one_or_none():
                break
            code = generate_voucher_code(prefix=payload.prefix or "")

        voucher = Voucher(
            plan_id=plan.id,
            code=code,
            status=VoucherStatus.GENERATED,
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        db.add(voucher)
        vouchers.append(voucher)

    await db.commit()
    for v in vouchers:
        await db.refresh(v)
    return vouchers


@router.post("/redeem")
async def redeem_voucher(
    payload: VoucherRedeem,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
):
    """Redeem a voucher code to activate a subscription."""
    result = await db.execute(
        select(Voucher).where(Voucher.code == payload.code.strip().upper())
    )
    voucher = result.scalar_one_or_none()

    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")

    if voucher.status != VoucherStatus.GENERATED:
        raise HTTPException(status_code=400, detail=f"Voucher already {voucher.status.value}")

    if voucher.expires_at and voucher.expires_at < datetime.now(timezone.utc):
        voucher.status = VoucherStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Voucher has expired")

    # Get plan
    plan_result = await db.execute(select(Plan).where(Plan.id == voucher.plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Get or create user
    user_result = await db.execute(select(User).where(User.phone_number == payload.phone_number))
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(
            full_name=f"Guest ({payload.phone_number})",
            phone_number=payload.phone_number,
            status=UserStatus.ACTIVE,
            is_verified=False,
        )
        db.add(user)
        await db.flush()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=plan.duration_hours)

    # Expire existing active subscriptions
    existing_subs = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
    )
    for sub in existing_subs.scalars().all():
        sub.status = SubscriptionStatus.EXPIRED

    # Create subscription
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        started_at=now,
        expires_at=expires_at,
        payment_reference=f"VOUCHER-{voucher.code}",
    )
    db.add(subscription)

    # Mark voucher as redeemed
    voucher.status = VoucherStatus.REDEEMED
    voucher.user_id = user.id
    voucher.redeemed_at = now

    # Create transaction
    transaction = Transaction(
        user_id=user.id,
        type=TransactionType.SUBSCRIPTION_PURCHASE,
        status=TransactionStatus.COMPLETED,
        amount=plan.price,
        currency="KES",
        description=f"Voucher redemption: {voucher.code}",
    )
    db.add(transaction)
    await db.commit()

    # Send SMS
    sms_message = build_subscription_sms(
        full_name=user.full_name,
        plan_name=plan.name,
        expires_at=expires_at,
        receipt=voucher.code,
    )
    background_tasks.add_task(send_sms, db, user.phone_number, sms_message, user.id)

    return {
        "success": True,
        "message": f"Voucher redeemed. Enjoy your {plan.name} internet!",
        "plan": plan.name,
        "expires_at": expires_at.isoformat(),
        "bandwidth_profile": plan.bandwidth_profile,
    }


@router.get("/", response_model=List[VoucherOut])
async def list_vouchers(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Voucher).order_by(Voucher.created_at.desc()))
    return result.scalars().all()


@router.get("/{voucher_id}", response_model=VoucherOut)
async def get_voucher(
    voucher_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Voucher).where(Voucher.id == voucher_id))
    voucher = result.scalar_one_or_none()
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")
    return voucher
