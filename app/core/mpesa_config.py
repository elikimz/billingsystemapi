import logging
import json
from sqlalchemy import select
from app.config.settings import settings
from app.database.database import AsyncSessionLocal
from app.models.models import SystemSetting

logger = logging.getLogger(__name__)

class MpesaConfig:
    """
    Robust M-Pesa configuration manager.
    Prioritizes Database settings, then Environment variables, then Defaults.
    Strictly handles environment switching to prevent sandbox/production mix-ups.
    """
    
    PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"
    SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"

    @classmethod
    async def get_setting(cls, key: str, default: str) -> str:
        """Fetch a single setting from the database with fallback."""
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
                setting = result.scalar_one_or_none()
                if setting and setting.value:
                    # Clean the value (remove whitespace/quotes)
                    val = str(setting.value).strip().strip("'").strip('"')
                    return val
        except Exception as e:
            logger.error(f"Database error fetching M-Pesa setting '{key}': {e}")
        return str(default).strip()

    @classmethod
    async def load(cls) -> dict:
        """Load the full M-Pesa configuration for the current request."""
        # 1. Determine Environment
        env_raw = await cls.get_setting("mpesa_env", settings.MPESA_ENV)
        env = env_raw.lower()
        
        # 2. Set Base URL strictly based on environment
        if env == "production":
            base_url = cls.PRODUCTION_BASE_URL
        else:
            base_url = cls.SANDBOX_BASE_URL
            
        # 3. Load Credentials
        config = {
            "env": env,
            "base_url": base_url,
            "consumer_key": await cls.get_setting("mpesa_consumer_key", settings.MPESA_CONSUMER_KEY),
            "consumer_secret": await cls.get_setting("mpesa_consumer_secret", settings.MPESA_CONSUMER_SECRET),
            "passkey": await cls.get_setting("mpesa_passkey", settings.MPESA_PASSKEY),
            "shortcode": await cls.get_setting("mpesa_shortcode", settings.MPESA_SHORTCODE),
            "callback_url": await cls.get_setting("mpesa_callback_url", settings.MPESA_CALLBACK_URL),
        }
        
        # Security check: Ensure we don't have sandbox URL in production
        if config["env"] == "production" and "sandbox" in config["base_url"]:
            logger.critical("SECURITY ALERT: Production environment active but base URL points to sandbox!")
            config["base_url"] = cls.PRODUCTION_BASE_URL
            
        logger.info(f"M-Pesa Config Loaded: Env={config['env']}, BaseURL={config['base_url']}, Shortcode={config['shortcode']}")
        return config
