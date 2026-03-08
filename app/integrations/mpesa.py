import httpx
import base64
import logging
from datetime import datetime, timezone
from app.config.settings import settings

logger = logging.getLogger(__name__)

MPESA_BASE_URLS = {
    "production": "https://api.safaricom.co.ke",
    "sandbox": "https://sandbox.safaricom.co.ke",
}


def get_mpesa_base_url() -> str:
    env = settings.MPESA_ENV.lower()
    return MPESA_BASE_URLS.get(env, MPESA_BASE_URLS["production"])


async def get_mpesa_access_token() -> str:
    """Fetch OAuth access token from Daraja API."""
    base_url = get_mpesa_base_url()
    credentials = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{base_url}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {encoded}"},
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


def generate_mpesa_password() -> tuple[str, str]:
    """Generate STK push password and timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
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
    base_url = get_mpesa_base_url()
    access_token = await get_mpesa_access_token()
    password, timestamp = generate_mpesa_password()

    # Normalize phone number to 254XXXXXXXXX format
    phone = phone_number.strip().replace("+", "").replace(" ", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif not phone.startswith("254"):
        phone = "254" + phone

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc,
    }

    logger.info(f"Initiating STK push to {phone} for KES {amount}")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        data = response.json()
        logger.info(f"STK push response: {data}")
        return data


async def query_stk_push_status(checkout_request_id: str) -> dict:
    """Query the status of an STK push transaction."""
    base_url = get_mpesa_base_url()
    access_token = await get_mpesa_access_token()
    password, timestamp = generate_mpesa_password()

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/mpesa/stkpushquery/v1/query",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        return response.json()
