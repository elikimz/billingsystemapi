from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal


# ========================
# AUTH SCHEMAS
# ========================

class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    phone_number: str = Field(..., min_length=10, max_length=20)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)


class UserLogin(BaseModel):
    phone_number: str
    password: str


class AdminLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    role: Optional[str] = None


# ========================
# USER SCHEMAS
# ========================

class UserOut(BaseModel):
    id: UUID
    full_name: str
    phone_number: str
    email: Optional[str]
    status: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


# ========================
# PLAN SCHEMAS
# ========================

class PlanCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0)
    duration_hours: int = Field(..., gt=0)
    bandwidth_profile: Optional[str] = None
    device_limit: int = Field(default=1, ge=1)
    is_voucher_enabled: bool = True
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    duration_hours: Optional[int] = None
    bandwidth_profile: Optional[str] = None
    device_limit: Optional[int] = None
    is_voucher_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class PlanOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    price: Decimal
    duration_hours: int
    bandwidth_profile: Optional[str]
    device_limit: int
    is_voucher_enabled: bool
    is_active: bool
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# SUBSCRIPTION SCHEMAS
# ========================

class SubscriptionCreate(BaseModel):
    plan_id: UUID
    phone_number: str = Field(..., min_length=10, max_length=20)
    mac_address: Optional[str] = None


class SubscriptionOut(BaseModel):
    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    started_at: Optional[datetime]
    expires_at: Optional[datetime]
    payment_reference: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# PAYMENT SCHEMAS
# ========================

class PaymentInitiate(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)
    plan_id: UUID
    mac_address: Optional[str] = None


class MpesaCallbackBody(BaseModel):
    Body: dict


class PaymentOut(BaseModel):
    id: UUID
    user_id: UUID
    plan_id: Optional[UUID]
    amount: Decimal
    status: str
    method: str
    checkout_request_id: Optional[str]
    merchant_request_id: Optional[str]
    mpesa_receipt_number: Optional[str]
    phone_number: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# VOUCHER SCHEMAS
# ========================

class VoucherGenerate(BaseModel):
    plan_id: UUID
    quantity: int = Field(default=1, ge=1, le=100)
    prefix: Optional[str] = None


class VoucherRedeem(BaseModel):
    code: str
    phone_number: str
    mac_address: Optional[str] = None


class VoucherOut(BaseModel):
    id: UUID
    code: str
    plan_id: UUID
    status: str
    expires_at: Optional[datetime]
    redeemed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# ADMIN SCHEMAS
# ========================

class AdminCreate(BaseModel):
    full_name: str
    email: str
    password: str = Field(..., min_length=8)
    role: str = "admin"


class AdminOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# ROUTER SCHEMAS
# ========================

class RouterCreate(BaseModel):
    name: str
    ip_address: str
    location: Optional[str] = None
    mikrotik_username: Optional[str] = None
    mikrotik_password: Optional[str] = None
    mikrotik_port: int = 8728


class RouterOut(BaseModel):
    id: UUID
    name: str
    ip_address: str
    location: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# SYSTEM SETTINGS SCHEMAS
# ========================

class SettingUpdate(BaseModel):
    value: str


class SettingOut(BaseModel):
    key: str
    value: Optional[str]
    scope: str
    description: Optional[str]
    is_encrypted: bool

    class Config:
        from_attributes = True


# ========================
# SMS LOG SCHEMAS
# ========================

class SMSLogOut(BaseModel):
    id: UUID
    phone_number: str
    message: str
    status: str
    provider: Optional[str]
    failure_reason: Optional[str]
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# AUDIT LOG SCHEMAS
# ========================

class AuditLogOut(BaseModel):
    id: UUID
    admin_user_id: Optional[UUID]
    action: str
    entity_type: str
    entity_id: Optional[str]
    details: Optional[str]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ========================
# DASHBOARD SCHEMAS
# ========================

class DashboardStats(BaseModel):
    total_users: int
    active_subscriptions: int
    total_revenue: Decimal
    total_payments: int
    active_plans: int
    total_vouchers: int
    redeemed_vouchers: int
