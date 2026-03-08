import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from app.database.database import AsyncSessionLocal, engine
from app.models.models import Base, AdminUser, AdminRole, SystemSetting, SettingScope
from app.core.security import hash_password
from app.config.settings import settings
from app.routers import auth, plans, payments, subscriptions, vouchers, admin, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def seed_default_admin():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AdminUser).limit(1))
        if not result.scalars().first():
            admin_user = AdminUser(
                full_name="Super Admin",
                email=settings.ADMIN_DEFAULT_EMAIL,
                password_hash=hash_password(settings.ADMIN_DEFAULT_PASSWORD),
                role=AdminRole.SUPER_ADMIN,
                is_active=True,
            )
            db.add(admin_user)
            await db.commit()
            logger.info(f"Default admin created: {settings.ADMIN_DEFAULT_EMAIL}")


async def seed_default_settings():
    defaults = [
        ("mpesa_consumer_key", settings.MPESA_CONSUMER_KEY, SettingScope.PAYMENT, "M-Pesa Consumer Key"),
        ("mpesa_consumer_secret", settings.MPESA_CONSUMER_SECRET, SettingScope.PAYMENT, "M-Pesa Consumer Secret"),
        ("mpesa_shortcode", settings.MPESA_SHORTCODE, SettingScope.PAYMENT, "M-Pesa Short Code"),
        ("mpesa_passkey", settings.MPESA_PASSKEY, SettingScope.PAYMENT, "M-Pesa Passkey"),
        ("mpesa_callback_url", settings.MPESA_CALLBACK_URL, SettingScope.PAYMENT, "M-Pesa Callback URL"),
        ("sms_mode", settings.SMS_MODE, SettingScope.SMS, "SMS Mode (sandbox/production)"),
        ("portal_name", "HotSpot Billing", SettingScope.GENERAL, "Portal display name"),
        ("currency", "KES", SettingScope.GENERAL, "Default currency"),
    ]
    async with AsyncSessionLocal() as db:
        for key, value, scope, description in defaults:
            result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
            if not result.scalar_one_or_none():
                db.add(SystemSetting(key=key, value=value, scope=scope, description=description))
        await db.commit()
    logger.info("Default system settings seeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WiFi Billing System API...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_default_admin()
        await seed_default_settings()
        logger.info("Startup complete")
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="WiFi Billing System API",
    description="Professional captive portal billing system with M-Pesa integration",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(plans.router, prefix=API_PREFIX)
app.include_router(payments.router, prefix=API_PREFIX)
app.include_router(subscriptions.router, prefix=API_PREFIX)
app.include_router(vouchers.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {"message": "WiFi Billing System API v2.0", "status": "running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
