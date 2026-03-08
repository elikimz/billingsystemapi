import httpx
import base64
import logging
import json
from datetime import datetime, timezone
from app.config.settings import settings

logger = logging.getLogger(__name__)

MPESA_BASE_URLS = {
    "production": "https://api.safaricom.co.ke",
    "sandbox": "https://sandbox.safaricom.co.ke",
}


def get_mpesa_base_url() -> str:
    env = settings.MPESA_ENV.lower()
    url = MPESA_BASE_URLS.get(env, MPESA_BASE_URLS["production"])
    logger.debug(f"Using M-Pesa environment: {env}, URL: {url}")
    return url


async def get_mpesa_access_token() -> str:
    """Fetch OAuth access token from Daraja API."""
    base_url = get_mpesa_base_url()
    credentials = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()

    url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    logger.info(f"Fetching M-Pesa access token from: {url}")
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Basic {encoded}"},
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get M-Pesa token. Status: {response.status_code}, Response: {response.text}")
                # Log detailed error for production debugging
                try:
                    error_data = response.json()
                    logger.error(f"M-Pesa Token Error Detail: {json.dumps(error_data)}")
                except:
                    pass
            
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching M-Pesa token: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching M-Pesa token: {str(e)}")
            raise


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
    
    try:
        access_token = await get_mpesa_access_token()
    except Exception as e:
        logger.error(f"Could not initiate STK push due to token failure: {str(e)}")
        return {"ResponseCode": "1", "errorMessage": f"Authentication failed: {str(e)}"}
        
    password, timestamp = generate_mpesa_password()

    # Normalize phone number to 254XXXXXXXXX format
    phone = phone_number.strip().replace("+", "").replace(" ", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone
    elif not phone.startswith("254"):
        # Default to prefixing if it doesn't match expected formats
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

    url = f"{base_url}/mpesa/stkpush/v1/processrequest"
    logger.info(f"Initiating STK push to {phone} for KES {amount} at {url}")
    logger.debug(f"STK Push Payload: {json.dumps({**payload, 'Password': '***'})}")

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
    base_url = get_mpesa_base_url()
    access_token = await get_mpesa_access_token()
    password, timestamp = generate_mpesa_password()

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
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
