from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.database.database import get_async_db
from app.models.models import Plan, PlanStatus, AuditLog
from app.schemas.schemas import PlanCreate, PlanUpdate, PlanOut
from app.core.deps import get_current_admin

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.get("/", response_model=List[PlanOut])
async def list_plans(db: AsyncSession = Depends(get_async_db)):
    """List all active plans (public endpoint for captive portal)."""
    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.price)
    )
    return result.scalars().all()


@router.get("/all", response_model=List[PlanOut])
async def list_all_plans(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    """List all plans including inactive (admin only)."""
    result = await db.execute(select(Plan).order_by(Plan.price))
    return result.scalars().all()


@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: UUID, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/", response_model=PlanOut, status_code=201)
async def create_plan(
    payload: PlanCreate,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    plan = Plan(**payload.model_dump())
    db.add(plan)
    # Audit log
    db.add(AuditLog(
        admin_user_id=admin.id,
        action="CREATE",
        entity_type="Plan",
        entity_id=None,
        details=f"Created plan: {payload.name}",
    ))
    await db.commit()
    await db.refresh(plan)
    return plan


@router.put("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    # Sync status field
    if plan.is_active:
        plan.status = PlanStatus.ACTIVE
    else:
        plan.status = PlanStatus.INACTIVE

    db.add(AuditLog(
        admin_user_id=admin.id,
        action="UPDATE",
        entity_type="Plan",
        entity_id=str(plan_id),
        details=f"Updated plan: {plan.name}",
    ))
    await db.commit()
    await db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan.is_active = False
    plan.status = PlanStatus.INACTIVE
    await db.commit()
