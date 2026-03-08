from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = "super_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # M-Pesa
    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_PASSKEY: str = ""
    MPESA_SHORTCODE: str = ""
    MPESA_CALLBACK_URL: str = "https://example.com/api/v1/payments/mpesa/callback"
    MPESA_ENV: str = "production"

    # SMS
    SMS_MODE: str = "sandbox"

    # Admin defaults
    ADMIN_DEFAULT_EMAIL: str = "admin@hotspot.local"
    ADMIN_DEFAULT_PASSWORD: str = "Admin@1234"

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
