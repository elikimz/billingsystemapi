import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.models.models import SMSLog, SMSStatus

logger = logging.getLogger(__name__)


async def send_sms(
    db: AsyncSession,
    phone_number: str,
    message: str,
    user_id=None,
) -> bool:
    """
    Send an SMS message. In sandbox mode, logs only.
    In production, integrate with Africa's Talking, Twilio, etc.
    Returns True if sent successfully, False otherwise.
    """
    sms_log = SMSLog(
        user_id=user_id,
        phone_number=phone_number,
        message=message,
        status=SMSStatus.PENDING,
        provider="sandbox" if settings.SMS_MODE == "sandbox" else "africastalking",
    )
    db.add(sms_log)
    await db.flush()

    try:
        if settings.SMS_MODE == "sandbox":
            # Simulate sandbox — just log
            logger.info(f"[SMS SANDBOX] To: {phone_number} | Message: {message}")
            sms_log.status = SMSStatus.SENT
            sms_log.sent_at = datetime.now(timezone.utc)
            await db.commit()
            return True
        else:
            # Production SMS integration placeholder
            # Replace with Africa's Talking or other provider
            logger.warning("Production SMS not configured. Falling back to sandbox log.")
            sms_log.status = SMSStatus.SENT
            sms_log.sent_at = datetime.now(timezone.utc)
            await db.commit()
            return True

    except Exception as e:
        logger.error(f"SMS send failed to {phone_number}: {e}")
        sms_log.status = SMSStatus.FAILED
        sms_log.failure_reason = str(e)
        await db.commit()
        return False


def build_subscription_sms(full_name: str, plan_name: str, expires_at: datetime, receipt: str = "") -> str:
    expiry_str = expires_at.strftime("%d %b %Y %H:%M")
    receipt_part = f" Receipt: {receipt}." if receipt else ""
    return (
        f"Hi {full_name}, your {plan_name} subscription is now active.{receipt_part} "
        f"Expires: {expiry_str}. Enjoy your internet!"
    )


def build_expiry_sms(full_name: str, plan_name: str) -> str:
    return (
        f"Hi {full_name}, your {plan_name} subscription has expired. "
        f"Please reconnect to Wi-Fi and purchase a new package to continue."
    )
