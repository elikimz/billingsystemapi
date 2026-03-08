import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.utcnow()


# =========================
# ENUMS
# =========================

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    PENDING = "pending"


class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPPORT = "support"
    FINANCE = "finance"


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REVERSED = "reversed"


class PaymentMethod(str, enum.Enum):
    MPESA = "mpesa"
    CASH = "cash"
    BANK = "bank"
    CARD = "card"


class TransactionType(str, enum.Enum):
    PAYMENT = "payment"
    SUBSCRIPTION_PURCHASE = "subscription_purchase"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    REFERRAL_BONUS = "referral_bonus"
    REFERRAL_REBATE = "referral_rebate"
    TASK_REWARD = "task_reward"
    COMMISSION = "commission"
    GIFT_REDEMPTION = "gift_redemption"
    WEALTH_FUND_MATURITY = "wealth_fund_maturity"
    WITHDRAWAL = "withdrawal"
    ADJUSTMENT = "adjustment"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class VoucherStatus(str, enum.Enum):
    GENERATED = "generated"
    ISSUED = "issued"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RouterStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    OFFLINE = "offline"


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    ENDED = "ended"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class SMSStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DELIVERED = "delivered"


class SettingScope(str, enum.Enum):
    PAYMENT = "payment"
    SMS = "sms"
    MIKROTIK = "mikrotik"
    GENERAL = "general"


# =========================
# MIXINS
# =========================

class TimestampMixin:
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class UUIDMixin:
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)


# =========================
# USERS
# =========================

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)

    status = Column(Enum(UserStatus), default=UserStatus.PENDING, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    current_plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True)
    referred_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    current_plan = relationship("Plan", foreign_keys=[current_plan_id])
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    vouchers = relationship("Voucher", back_populates="user")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("HotspotSession", back_populates="user", cascade="all, delete-orphan")
    sms_logs = relationship("SMSLog", back_populates="user", cascade="all, delete-orphan")

    referrer = relationship("User", remote_side="User.id", backref="referrals")


class AdminUser(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "admin_users"

    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(AdminRole), default=AdminRole.ADMIN, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


# =========================
# PLANS / PACKAGES
# =========================

class Plan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "plans"

    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    price = Column(Numeric(12, 2), nullable=False)
    duration_hours = Column(Integer, nullable=False)
    bandwidth_profile = Column(String(100), nullable=True)

    device_limit = Column(Integer, default=1, nullable=False)
    is_voucher_enabled = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(Enum(PlanStatus), default=PlanStatus.ACTIVE, nullable=False)

    subscriptions = relationship("Subscription", back_populates="plan")
    payments = relationship("Payment", back_populates="plan")
    vouchers = relationship("Voucher", back_populates="plan")


# =========================
# ROUTERS / HOTSPOTS
# =========================

class Router(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "routers"

    name = Column(String(255), nullable=False, unique=True)
    location = Column(String(255), nullable=True)
    ip_address = Column(String(100), nullable=False)
    api_port = Column(Integer, default=8728, nullable=False)
    username = Column(String(100), nullable=False)
    password_encrypted = Column(Text, nullable=False)

    router_identity = Column(String(255), nullable=True)
    hotspot_name = Column(String(255), nullable=True)
    status = Column(Enum(RouterStatus), default=RouterStatus.ACTIVE, nullable=False)

    subscriptions = relationship("Subscription", back_populates="router")
    sessions = relationship("HotspotSession", back_populates="router")


# =========================
# PAYMENTS
# =========================

class Payment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payments"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="KES", nullable=False)

    method = Column(Enum(PaymentMethod), default=PaymentMethod.MPESA, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)

    phone_number = Column(String(20), nullable=True)
    merchant_request_id = Column(String(255), nullable=True, index=True)
    checkout_request_id = Column(String(255), nullable=True, index=True)
    mpesa_receipt_number = Column(String(255), nullable=True, unique=True)
    external_reference = Column(String(255), nullable=True, index=True)

    paid_at = Column(DateTime, nullable=True)
    callback_payload = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)

    user = relationship("User", back_populates="payments")
    plan = relationship("Plan", back_populates="payments")


# =========================
# VOUCHERS
# =========================

class Voucher(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vouchers"

    code = Column(String(100), unique=True, nullable=False, index=True)
    pin = Column(String(50), nullable=True)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True)

    status = Column(Enum(VoucherStatus), default=VoucherStatus.GENERATED, nullable=False)
    issued_at = Column(DateTime, nullable=True)
    redeemed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    generated_by_admin_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="vouchers")
    plan = relationship("Plan", back_populates="vouchers")


# =========================
# SUBSCRIPTIONS
# =========================

class Subscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    router_id = Column(UUID(as_uuid=True), ForeignKey("routers.id"), nullable=True)

    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False)

    activated_at = Column(DateTime, nullable=True)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("vouchers.id"), nullable=True)

    mikrotik_username = Column(String(255), nullable=True)
    mikrotik_profile = Column(String(100), nullable=True)
    sync_status = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    router = relationship("Router", back_populates="subscriptions")
    payment = relationship("Payment", foreign_keys=[payment_id])
    voucher = relationship("Voucher", foreign_keys=[voucher_id])

    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_subscription_payment_id"),
    )


# =========================
# TRANSACTIONS
# =========================

class Transaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "transactions"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)

    type = Column(Enum(TransactionType), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.COMPLETED, nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="KES", nullable=False)
    description = Column(Text, nullable=True)

    user = relationship("User", back_populates="transactions")


# =========================
# DEVICES
# =========================

class Device(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "devices"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    mac_address = Column(String(50), unique=True, nullable=False, index=True)
    device_name = Column(String(255), nullable=True)
    device_type = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="devices")


# =========================
# HOTSPOT SESSIONS
# =========================

class HotspotSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "hotspot_sessions"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    router_id = Column(UUID(as_uuid=True), ForeignKey("routers.id"), nullable=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=True)

    mac_address = Column(String(50), nullable=True, index=True)
    ip_address = Column(String(100), nullable=True)
    username = Column(String(255), nullable=True)

    started_at = Column(DateTime, default=utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    session_status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE, nullable=False)

    bytes_in = Column(Integer, default=0, nullable=False)
    bytes_out = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="sessions")
    router = relationship("Router", back_populates="sessions")


# =========================
# REFERRALS
# =========================

class Referral(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "referrals"

    referrer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    level = Column(String(1), nullable=False)
    percentage = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class ReferralCommission(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "referral_commissions"

    referrer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)

    level = Column(String(1), nullable=False)
    percentage = Column(Float, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(50), default="credited", nullable=False)


# =========================
# SMS LOGS
# =========================

class SMSLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sms_logs"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    message = Column(Text, nullable=False)

    status = Column(Enum(SMSStatus), default=SMSStatus.PENDING, nullable=False)
    provider = Column(String(100), nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    failure_reason = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sms_logs")


# =========================
# SETTINGS
# =========================

class SystemSetting(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "system_settings"

    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    scope = Column(Enum(SettingScope), default=SettingScope.GENERAL, nullable=False)
    is_encrypted = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)


# =========================
# AUDIT LOGS
# =========================

class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    admin_user_id = Column(UUID(as_uuid=True), ForeignKey("admin_users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(100), nullable=True)