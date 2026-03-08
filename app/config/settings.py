from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://neondb_owner:npg_pKPFiOc0Vf8C@ep-green-mountain-adazce6s-pooler.c-2.us-east-1.aws.neon.tech/neondb"
    SECRET_KEY: str = "super_secret_key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # M-Pesa - Production Credentials Strictly Hardcoded
    MPESA_ENV: str = "production"
    MPESA_CONSUMER_KEY: str = "LM6MxKjJXDzqlxYK7ej1A6DWUd8sVJ6XYf22ByFh4R4rgykA"
    MPESA_CONSUMER_SECRET: str = "MAjliohCqtGGvshySY8RkHZSF88eemW1Wp77PjwxO3ci0m7242fdGGEXv2TQkIjk"
    MPESA_PASSKEY: str = "d4f1dd629fbd7638a5272362f3b42057bf5fed09bca901db242b0ac7e88ee993"
    MPESA_SHORTCODE: str = "3538431"
    MPESA_CALLBACK_URL: str = "https://api.elijahkimani.com/api/v1/payments/mpesa/callback"

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
