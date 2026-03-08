import httpx
import base64
import logging
import json
from datetime import datetime, timezone
from sqlalchemy import select
from app.config.settings import settings
from app.database.database import AsyncSessionLocal
from app.models.models import SystemSetting

logger = logging.getLogger(__name__)

MPESA_BASE_URLS = {
    "production": "https://api.safaricom.co.ke",
    "sandbox": "https://sandbox.safaricom.co.ke",
}

async def get_mpesa_setting(key: str, default: str) -> str:
    """Retrieve a setting from the database or fall back to environment variables."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
    except Exception as e:
        logger.error(f"Error fetching setting {key} from DB: {e}")
    return default

async def get_mpesa_config() -> dict:
    """Load all M-Pesa configuration, prioritizing database settings."""
    # We check MPESA_ENV first to determine the base URL
    mpesa_env = await get_mpesa_setting("mpesa_env", settings.MPESA_ENV)
    
    config = {
        "env": mpesa_env.lower(),
        "consumer_key": await get_mpesa_setting("mpesa_consumer_key", settings.MPESA_CONSUMER_KEY),
        "consumer_secret": await get_mpesa_setting("mpesa_consumer_secret", settings.MPESA_CONSUMER_SECRET),
        "passkey": await get_mpesa_setting("mpesa_passkey", settings.MPESA_PASSKEY),
        "shortcode": await get_mpesa_setting("mpesa_shortcode", settings.MPESA_SHORTCODE),
    }
    
    config["base_url"] = MPESA_BASE_URLS.get(config["env"], MPESA_BASE_URLS["production"])
    return config

async def get_mpesa_access_token() -> str:
    """Fetch OAuth access token from Daraja API."""
    config = await get_mpesa_config()
    base_url = config["base_url"]
    credentials = f"{config['consumer_key']}:{config['consumer_secret']}"
    encoded = base64.b64encode(credentials.encode()).decode()

    url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    logger.info(f"Fetching M-Pesa access token from: {url} (Env: {config['env']})")
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Basic {encoded}"},
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get M-Pesa token. Status: {response.status_code}, Response: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching M-Pesa token from {url}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching M-Pesa token: {str(e)}")
            raise

def generate_mpesa_password(shortcode: str, passkey: str) -> tuple[str, str]:
    """Generate STK push password and timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp

async def initiate_stk_push(
    phone_number: str,
    amount: float,
    account_reference: str,
    transaction_desc: str,
    callback_url: str,
) -> dict:
    """Initiate M-Pesa STK push payment."""
    config = await get_mpesa_config()
    base_url = config["base_url"]
    
    try:
        access_token = await get_mpesa_access_token()
    except Exception as e:
        logger.error(f"Could not initiate STK push due to token failure: {str(e)}")
        return {"ResponseCode": "1", "errorMessage": f"Authentication failed: {str(e)}"}
        
    password, timestamp = generate_mpesa_password(config["shortcode"], config["passkey"])

    # Normalize phone number to 254XXXXXXXXX format
    phone = phone_number.strip().replace("+", "").replace(" ", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone
    elif not phone.startswith("254"):
        phone = "254" + phone

    payload = {
        "BusinessShortCode": config["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": config["shortcode"],
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc,
    }

    url = f"{base_url}/mpesa/stkpush/v1/processrequest"
    logger.info(f"Initiating STK push to {phone} for KES {amount} at {url}")

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            
            data = response.json()
            if response.status_code != 200:
                logger.error(f"STK push failed. Status: {response.status_code}, Response: {response.text}")
            else:
                logger.info(f"STK push response: {data}")
                
            return data
        except Exception as e:
            logger.error(f"Error calling STK push API: {str(e)}")
            return {"ResponseCode": "1", "errorMessage": f"API call failed: {str(e)}"}

async def query_stk_push_status(checkout_request_id: str) -> dict:
    """Query the status of an STK push transaction."""
    config = await get_mpesa_config()
    base_url = config["base_url"]
    access_token = await get_mpesa_access_token()
    password, timestamp = generate_mpesa_password(config["shortcode"], config["passkey"])

    payload = {
        "BusinessShortCode": config["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    url = f"{base_url}/mpesa/stkpushquery/v1/query"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        return response.json()
