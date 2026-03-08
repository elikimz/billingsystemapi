import httpx
import base64
import logging
import json
import re
from datetime import datetime, timezone
from app.core.mpesa_config import MpesaConfig

logger = logging.getLogger(__name__)

async def get_mpesa_access_token() -> str:
    """Fetch OAuth access token from Daraja API with production/sandbox handling."""
    config = await MpesaConfig.load()
    base_url = config["base_url"]
    
    # Credentials encoding
    credentials = f"{config['consumer_key']}:{config['consumer_secret']}"
    encoded = base64.b64encode(credentials.encode()).decode()

    # Request preparation
    url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    logger.info(f"M-Pesa OAuth Request: {url} (Env: {config['env']})")
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Basic {encoded}"},
            )
            
            # Log full Safaricom response on failure
            if response.status_code != 200:
                logger.error(f"M-Pesa OAuth Failed! Status: {response.status_code}")
                logger.error(f"Safaricom Response Body: {response.text}")
                
                # Check for specific 400 Bad Request common causes
                if "invalid_client" in response.text:
                    logger.error("Probable Cause: Invalid Consumer Key or Secret.")
                elif "sandbox" in url and config["env"] == "production":
                    logger.error("Probable Cause: Sandbox URL used for Production credentials.")
            
            response.raise_for_status()
            data = response.json()
            return data["access_token"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status Error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Safaricom OAuth Error: {e.response.text}")
        except Exception as e:
            logger.error(f"Unexpected M-Pesa OAuth Error: {str(e)}")
            raise Exception(f"Internal OAuth Failure: {str(e)}")

def generate_mpesa_password(shortcode: str, passkey: str) -> tuple[str, str]:
    """Generate STK push password and timestamp."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp

def normalize_phone_number(phone: str) -> str:
    """Normalize phone number to 254XXXXXXXXX format."""
    # Remove all non-numeric characters
    clean = re.sub(r"\D", "", phone)
    
    if clean.startswith("0"):
        clean = "254" + clean[1:]
    elif clean.startswith("7") or clean.startswith("1"):
        clean = "254" + clean
    elif clean.startswith("+254"):
        clean = clean[1:]
    elif not clean.startswith("254") and len(clean) == 9:
        clean = "254" + clean
        
    # Ensure it's exactly 12 digits
    if len(clean) != 12 or not clean.startswith("254"):
        logger.warning(f"Phone number normalization result might be invalid: {clean}")
        
    return clean

async def initiate_stk_push(
    phone_number: str,
    amount: float,
    account_reference: str,
    transaction_desc: str,
    callback_url: str,
) -> dict:
    """Initiate M-Pesa STK push payment with strict environment handling."""
    config = await MpesaConfig.load()
    base_url = config["base_url"]
    
    try:
        access_token = await get_mpesa_access_token()
    except Exception as e:
        logger.error(f"STK Push aborted: Token failure - {str(e)}")
        return {"ResponseCode": "1", "errorMessage": f"M-Pesa Authentication failed: {str(e)}"}
        
    password, timestamp = generate_mpesa_password(config["shortcode"], config["passkey"])
    phone = normalize_phone_number(phone_number)

    payload = {
        "BusinessShortCode": config["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": config["shortcode"],
        "PhoneNumber": phone,
        "CallBackURL": callback_url or config["callback_url"],
        "AccountReference": account_reference,
        "TransactionDesc": transaction_desc,
    }

    url = f"{base_url}/mpesa/stkpush/v1/processrequest"
    logger.info(f"STK Push Request: {url} (Phone: {phone}, Amount: {amount}, Env: {config['env']})")
    # Log secured payload for debugging
    logger.debug(f"Payload (Secured): {json.dumps({**payload, 'Password': '***'})}")

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
            if response.status_code != 200 or data.get("ResponseCode") != "0":
                logger.error(f"STK Push Failed! Status: {response.status_code}")
                logger.error(f"Safaricom Response Body: {response.text}")
                return {
                    "ResponseCode": data.get("ResponseCode", str(response.status_code)),
                    "errorMessage": data.get("errorMessage", data.get("ResponseDescription", "Safaricom API Error")),
                    "details": data
                }
            
            logger.info(f"STK Push Success: {data.get('ResponseDescription')} (CheckoutID: {data.get('CheckoutRequestID')})")
            return data
            
        except Exception as e:
            logger.error(f"STK Push API Call Error: {str(e)}")
            return {"ResponseCode": "1", "errorMessage": f"Connection to Safaricom failed: {str(e)}"}

async def query_stk_push_status(checkout_request_id: str) -> dict:
    """Query the status of an STK push transaction."""
    config = await MpesaConfig.load()
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
    logger.info(f"STK Query Request: {url} (CheckoutID: {checkout_request_id})")
    
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
