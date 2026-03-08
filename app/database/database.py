from asyncio import Task, tasks
import ssl
import os
from dotenv import load_dotenv

from sqlalchemy import Transaction
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Load environment variables
load_dotenv()

# Get DB URL
DATABASE_URL = os.getenv("DATABASE_URL")
assert DATABASE_URL is not None, "❌ DATABASE_URL not loaded from .env"

# --- SSL Context (optional for cloud DBs like Supabase or PlanetScale) ---
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# --- Async Engine ---
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    connect_args={"ssl": ssl_context}
)

# --- SessionMaker ---
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # ✅ FIX: prevents attributes from expiring after commit
    autocommit=False,
    autoflush=False,
)

# --- Declarative Base ---
Base = declarative_base()

# --- Dependency for FastAPI routes ---
async def get_async_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()




from app.models.models import (
    # Users
    User,
    AdminUser,

    # Plans / Packages
    Plan,

    # Subscriptions
    Subscription,

    # Payments / Billing
    Payment,
    Transaction,

    # Routers / MikroTik
    Router,

    # Vouchers
    Voucher,

    # Devices
    Device,

    # Sessions
    HotspotSession,

    # Referrals
    Referral,
    ReferralCommission,

    # SMS
    SMSLog,

    # Settings / Config
    SystemSetting,

    # Audit Logs
    AuditLog,
)



__all__ = ["engine", "AsyncSessionLocal", "Base", "get_async_db"]