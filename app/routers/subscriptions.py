import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from datetime import datetime, timezone
from app.database.database import get_async_db
from app.models.models import Subscription, SubscriptionStatus, User, Plan
from app.schemas.schemas import SubscriptionOut
from app.core.deps import get_current_user, get_current_admin

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])
logger = logging.getLogger(__name__)


@router.get("/my", response_model=List[SubscriptionOut])
async def get_my_subscriptions(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user's subscriptions."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == current_user.id)
        .order_by(Subscription.created_at.desc())
    )
    return result.scalars().all()


@router.get("/active/check")
async def check_active_subscription(
    phone_number: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Check if a phone number has an active subscription (used by captive portal)."""
    result = await db.execute(
        select(User).where(User.phone_number == phone_number)
    )
    user = result.scalar_one_or_none()
    if not user:
        return {"active": False, "message": "No user found"}

    now = datetime.utcnow()
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > now,
        )
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription:
        # Fetch plan
        plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
        plan = plan_result.scalar_one_or_none()
        return {
            "active": True,
            "subscription_id": str(subscription.id),
            "plan": plan.name if plan else None,
            "expires_at": subscription.expires_at.isoformat(),
            "bandwidth_profile": plan.bandwidth_profile if plan else None,
        }

    # Check for expired subscriptions and update them
    expired_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at <= now,
        )
    )
    for expired_sub in expired_result.scalars().all():
        expired_sub.status = SubscriptionStatus.EXPIRED
    await db.commit()

    return {"active": False, "message": "No active subscription"}


@router.get("/", response_model=List[SubscriptionOut])
async def list_all_subscriptions(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    """List all subscriptions (admin only)."""
    result = await db.execute(
        select(Subscription).order_by(Subscription.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{subscription_id}", response_model=SubscriptionOut)
async def get_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.post("/{subscription_id}/cancel", status_code=200)
async def cancel_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.status = SubscriptionStatus.CANCELLED
    await db.commit()
    return {"message": "Subscription cancelled"}
