import httpx
import base64
import logging
import json
import re
from datetime import datetime, timezone
from app.core.mpesa_config import MpesaConfig

logger = logging.getLogger(__name__)

async def get_mpesa_access_token() -> str:
    """Fetch OAuth access token from Daraja API with strict production handling."""
    config = await MpesaConfig.load()
    base_url = config["base_url"]
    
    # Credentials encoding
    credentials = f"{config['consumer_key']}:{config['consumer_secret']}"
    encoded = base64.b64encode(credentials.encode()).decode()

    # Request preparation
    url = f"{base_url}/oauth/v1/generate?grant_type=client_credentials"
    logger.info(f"M-Pesa OAuth: REQUEST {url} (ENV: {config['env']})")
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Basic {encoded}"},
            )
            
            # Log full Safaricom response on failure
            if response.status_code != 200:
                logger.error(f"M-Pesa OAuth: FAILED Status={response.status_code}")
                logger.error(f"M-Pesa OAuth: RESPONSE BODY {response.text}")
                
                if "invalid_client" in response.text:
                    logger.error("M-Pesa OAuth: Invalid Consumer Key or Secret.")
                elif "sandbox" in url and config["env"] == "production":
                    logger.error("M-Pesa OAuth: Sandbox URL used for Production credentials.")
            
            response.raise_for_status()
            data = response.json()
            logger.info("M-Pesa OAuth: SUCCESS Token generated.")
            return data["access_token"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"M-Pesa OAuth: HTTP ERROR {e.response.status_code} - {e.response.text}")
            raise Exception(f"Safaricom OAuth Error: {e.response.text}")
        except Exception as e:
            logger.error(f"M-Pesa OAuth: UNEXPECTED ERROR {str(e)}")
            raise Exception(f"Internal OAuth Failure: {str(e)}")

def generate_mpesa_password(shortcode: str, passkey: str) -> tuple[str, str]:
    """Generate STK push password and timestamp."""
    # Use EAT (UTC+3) for timestamp as Safaricom is in Kenya
    # However, Daraja usually accepts UTC if consistent. Let's stick to UTC for now but ensure it's formatted correctly.
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
    elif (clean.startswith("7") or clean.startswith("1")) and len(clean) == 9:
        clean = "254" + clean
    elif clean.startswith("254") and len(clean) == 12:
        pass
    elif clean.startswith("+254"):
        clean = clean[1:]
    
    # Final check: Must be 12 digits and start with 254
    if len(clean) != 12 or not clean.startswith("254"):
        logger.warning(f"Phone Normalization: Result {clean} may be invalid for input {phone}")
        
    return clean

async def initiate_stk_push(
    phone_number: str,
    amount: float,
    account_reference: str,
    transaction_desc: str,
    callback_url: str,
) -> dict:
    """Initiate M-Pesa STK push payment with strict logging and response validation."""
    config = await MpesaConfig.load()
    base_url = config["base_url"]
    
    try:
        access_token = await get_mpesa_access_token()
    except Exception as e:
        logger.error(f"STK Push: ABORTED Token failure - {str(e)}")
        return {"ResponseCode": "1", "errorMessage": f"M-Pesa Authentication failed: {str(e)}"}
        
    password, timestamp = generate_mpesa_password(config["shortcode"], config["passkey"])
    phone = normalize_phone_number(phone_number)

    # Determine TransactionType: 
    # CustomerPayBillOnline for Paybills
    # CustomerBuyGoodsOnline for Till Numbers
    # Most ShortCodes of 6-7 digits are Paybills. 
    # Let's default to CustomerPayBillOnline but make it robust.
    transaction_type = "CustomerPayBillOnline"
    
    payload = {
        "BusinessShortCode": config["shortcode"],
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": transaction_type,
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": config["shortcode"], # For Paybill, PartyB is the ShortCode
        "PhoneNumber": phone,
        "CallBackURL": callback_url or config["callback_url"],
        "AccountReference": account_reference[:12], # Safaricom limit is often 12 chars
        "TransactionDesc": transaction_desc[:20],
    }

    url = f"{base_url}/mpesa/stkpush/v1/processrequest"
    logger.info(f"STK Push: REQUEST {url} (PHONE: {phone}, AMOUNT: {amount}, ENV: {config['env']})")
    # Log payload without secrets
    debug_payload = {**payload, 'Password': '***'}
    logger.info(f"STK Push: PAYLOAD {json.dumps(debug_payload)}")

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
            logger.info(f"STK Push: RESPONSE BODY {response.text}")

            if response.status_code != 200 or data.get("ResponseCode") != "0":
                logger.error(f"STK Push: REJECTED Status={response.status_code} ResponseCode={data.get('ResponseCode')}")
                # If PayBill fails, try BuyGoods if the error suggests it
                if "invalid" in response.text.lower() and transaction_type == "CustomerPayBillOnline":
                    logger.info("STK Push: Retrying with CustomerBuyGoodsOnline...")
                    payload["TransactionType"] = "CustomerBuyGoodsOnline"
                    # For BuyGoods, PartyB is often the Store Number or the same ShortCode
                    # Let's try just changing the type first
                    response = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                    )
                    data = response.json()
                    logger.info(f"STK Push Retry: RESPONSE BODY {response.text}")
                    if response.status_code == 200 and data.get("ResponseCode") == "0":
                        logger.info(f"STK Push Success (BuyGoods): {data.get('ResponseDescription')}")
                        return data

                return {
                    "ResponseCode": data.get("ResponseCode", str(response.status_code)),
                    "errorMessage": data.get("errorMessage", data.get("ResponseDescription", "Safaricom API Error")),
                    "details": data
                }
            
            logger.info(f"STK Push: ACCEPTED Description={data.get('ResponseDescription')} CheckoutID={data.get('CheckoutRequestID')}")
            return data
            
        except Exception as e:
            logger.error(f"STK Push: API ERROR {str(e)}")
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
    logger.info(f"STK Query: REQUEST {url} (CheckoutID: {checkout_request_id})")
    
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
