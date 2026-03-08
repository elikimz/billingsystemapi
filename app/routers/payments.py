import logging
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from datetime import datetime, timedelta, timezone
from app.database.database import get_async_db
from app.models.models import (
    User, Plan, Payment, Subscription, Transaction, Device,
    PaymentStatus, PaymentMethod, SubscriptionStatus, TransactionType, TransactionStatus,
    UserStatus
)
from app.schemas.schemas import PaymentInitiate, PaymentOut
from app.integrations.mpesa import MpesaService
from app.integrations.sms import send_sms, build_subscription_sms
from app.config.settings import settings
from app.core.deps import get_current_admin, get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])
logger = logging.getLogger(__name__)

async def get_or_create_user(db: AsyncSession, phone_number: str) -> User:
    """Get existing user by phone or create a guest user."""
    result = await db.execute(select(User).where(User.phone_number == phone_number))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            full_name=f"Guest ({phone_number})",
            phone_number=phone_number,
            status=UserStatus.ACTIVE,
            is_verified=False,
        )
        db.add(user)
        await db.flush()
    return user

@router.post("/initiate")
async def initiate_payment(
    payload: PaymentInitiate,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Initiate M-Pesa STK push for a plan subscription.
    Strictly reports success ONLY if Safaricom accepts the request.
    """
    # 1. Validate plan
    result = await db.execute(select(Plan).where(Plan.id == payload.plan_id, Plan.is_active == True))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")

    # 2. Get or create user
    user = await get_or_create_user(db, payload.phone_number)

    # 3. Prevent duplicate pending payments
    existing = await db.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == PaymentStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A pending payment already exists. Please check your phone or wait.")

    # 4. Create initial payment record
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        amount=plan.price,
        currency="KES",
        method=PaymentMethod.MPESA,
        status=PaymentStatus.PENDING,
        phone_number=payload.phone_number,
    )
    db.add(payment)
    await db.flush()

    # 5. Initiate STK push with Safaricom
    try:
        stk_response = await MpesaService.initiate_stk_push(
            phone_number=payload.phone_number,
            amount=float(plan.price),
            account_ref=f"SUB-{str(payment.id)[:8].upper()}",
            desc=f"WiFi - {plan.name}",
            callback_url=settings.MPESA_CALLBACK_URL,
        )

        # 6. Process response
        if stk_response.get("ResponseCode") == "0":
            payment.checkout_request_id = stk_response.get("CheckoutRequestID")
            payment.merchant_request_id = stk_response.get("MerchantRequestID")
            await db.commit()
            
            logger.info(f"Payment {payment.id} initiated successfully. CheckoutID: {payment.checkout_request_id}")
            
            return {
                "success": True,
                "message": "STK push sent. Enter your M-Pesa PIN on your phone.",
                "payment_id": str(payment.id),
                "checkout_request_id": payment.checkout_request_id,
                "amount": float(plan.price),
                "plan": plan.name,
            }
        else:
            # Mark as failed if Safaricom rejects
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = stk_response.get("errorMessage", "STK push rejected by Safaricom")
            await db.commit()
            
            logger.error(f"Payment {payment.id} rejected by Safaricom: {stk_response}")
            
            raise HTTPException(
                status_code=400,
                detail=stk_response.get("errorMessage", "STK push failed. Check your phone or try again."),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment {payment.id} initiation error: {str(e)}", exc_info=True)
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Payment initiation failed: {str(e)}")

@router.post("/mpesa/callback")
async def mpesa_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
):
    """Handle M-Pesa payment callback from Daraja."""
    try:
        body = await request.json()
        logger.info(f"M-Pesa callback received: {body}")
    except Exception:
        logger.error("Failed to parse M-Pesa callback body")
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    try:
        stk_callback = body.get("Body", {}).get("stkCallback", {})
        result_code = stk_callback.get("ResultCode")
        checkout_request_id = stk_callback.get("CheckoutRequestID")

        if not checkout_request_id:
            logger.warning("No CheckoutRequestID in callback")
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        # Find payment record
        result = await db.execute(
            select(Payment).where(Payment.checkout_request_id == checkout_request_id)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            logger.warning(f"Payment not found for CheckoutRequestID: {checkout_request_id}")
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        # Prevent duplicate processing
        if payment.status != PaymentStatus.PENDING:
            logger.info(f"Payment {payment.id} already processed. Skipping.")
            return {"ResultCode": 0, "ResultDesc": "Accepted"}

        # Store callback payload
        payment.callback_payload = body

        if result_code == 0:
            # Payment successful
            callback_metadata = stk_callback.get("CallbackMetadata", {}).get("Item", [])
            metadata = {item["Name"]: item.get("Value") for item in callback_metadata}

            payment.status = PaymentStatus.SUCCESS
            payment.paid_at = datetime.now(timezone.utc)
            payment.mpesa_receipt_number = metadata.get("MpesaReceiptNumber")
            payment.external_reference = metadata.get("MpesaReceiptNumber")

            # Activate subscription
            plan_result = await db.execute(select(Plan).where(Plan.id == payment.plan_id))
            plan = plan_result.scalar_one_or_none()

            user_result = await db.execute(select(User).where(User.id == payment.user_id))
            user = user_result.scalar_one_or_none()

            if plan and user:
                now = datetime.now(timezone.utc)
                expires_at = now + timedelta(hours=plan.duration_hours)

                # Deactivate existing active subscriptions
                existing_subs = await db.execute(
                    select(Subscription).where(
                        Subscription.user_id == user.id,
                        Subscription.status == SubscriptionStatus.ACTIVE,
                    )
                )
                for sub in existing_subs.scalars().all():
                    sub.status = SubscriptionStatus.EXPIRED

                # Create new subscription
                subscription = Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    started_at=now,
                    expires_at=expires_at,
                    payment_id=payment.id,
                    payment_reference=payment.mpesa_receipt_number,
                )
                db.add(subscription)

                # Update user state
                user.current_plan_id = plan.id
                user.status = UserStatus.ACTIVE

                # Create transaction record
                transaction = Transaction(
                    user_id=user.id,
                    payment_id=payment.id,
                    type=TransactionType.SUBSCRIPTION_PURCHASE,
                    status=TransactionStatus.COMPLETED,
                    amount=payment.amount,
                    currency="KES",
                    description=f"Subscribed to {plan.name}",
                )
                db.add(transaction)
                
                await db.commit()
                logger.info(f"Subscription activated for {user.phone_number} on plan {plan.name}")

                # Send SMS confirmation
                sms_message = build_subscription_sms(
                    full_name=user.full_name,
                    plan_name=plan.name,
                    expires_at=expires_at,
                    receipt=payment.mpesa_receipt_number or "",
                )
                background_tasks.add_task(send_sms, db, user.phone_number, sms_message, user.id)
            else:
                logger.error(f"Plan or user not found for payment {payment.id}")
                await db.commit()
        else:
            # Payment failed or cancelled by user
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = stk_callback.get("ResultDesc", "Cancelled by user")
            await db.commit()
            logger.info(f"Payment {payment.id} failed: {payment.failure_reason}")

    except Exception as e:
        logger.error(f"Error processing M-Pesa callback: {str(e)}", exc_info=True)
        await db.rollback()

    return {"ResultCode": 0, "ResultDesc": "Accepted"}

@router.get("/status/{payment_id}")
async def check_payment_status(payment_id: UUID, db: AsyncSession = Depends(get_async_db)):
    """Check the status of a payment by ID."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": float(payment.amount),
        "mpesa_receipt": payment.mpesa_receipt_number,
        "failure_reason": payment.failure_reason,
        "created_at": payment.created_at.isoformat(),
        "is_final": payment.status in [PaymentStatus.SUCCESS, PaymentStatus.FAILED]
    }

@router.get("/my", response_model=List[PaymentOut])
async def my_payments(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    """List current user's payments."""
    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
    )
    return result.scalars().all()

@router.get("/", response_model=List[PaymentOut])
async def list_payments(
    db: AsyncSession = Depends(get_async_db),
    admin=Depends(get_current_admin),
):
    """List all payments (admin only)."""
    result = await db.execute(select(Payment).order_by(Payment.created_at.desc()))
    return result.scalars().all()
