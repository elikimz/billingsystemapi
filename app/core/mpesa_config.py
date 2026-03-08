import logging
import json
from app.config.settings import settings

logger = logging.getLogger(__name__)

class MpesaConfig:
    """
    Refactored M-Pesa configuration manager.
    Now strictly reads from backend configuration (settings.py) to avoid 
    any issues with database/admin settings overrides.
    """
    
    PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"
    SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"

    @classmethod
    async def load(cls) -> dict:
        """Load the full M-Pesa configuration from backend settings."""
        # Force production as requested, but allow override via settings if necessary
        env = settings.MPESA_ENV.lower() if hasattr(settings, 'MPESA_ENV') else "production"
        
        # Set Base URL strictly based on environment
        if env == "production":
            base_url = cls.PRODUCTION_BASE_URL
        else:
            base_url = cls.SANDBOX_BASE_URL
            
        # Load Credentials strictly from settings.py
        config = {
            "env": env,
            "base_url": base_url,
            "consumer_key": settings.MPESA_CONSUMER_KEY,
            "consumer_secret": settings.MPESA_CONSUMER_SECRET,
            "passkey": settings.MPESA_PASSKEY,
            "shortcode": settings.MPESA_SHORTCODE,
            "callback_url": settings.MPESA_CALLBACK_URL,
        }
        
        # Log active environment and URLs for clarity (avoiding secrets)
        logger.info(f"M-Pesa Config: ENV={config['env']}, BASE_URL={config['base_url']}, SHORTCODE={config['shortcode']}")
        
        return config
