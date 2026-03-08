import httpx
import base64
import logging
import json
import re
from datetime import datetime, timezone
from app.config.settings import settings

logger = logging.getLogger(__name__)

class MpesaService:
    """
    Redesigned M-Pesa Service for production-ready STK Push flow.
    Strictly uses production endpoints and credentials from backend config.
    """
    
    BASE_URL = "https://api.safaricom.co.ke"
    OAUTH_ENDPOINT = "/oauth/v1/generate?grant_type=client_credentials"
    STK_PUSH_ENDPOINT = "/mpesa/stkpush/v1/processrequest"
    STK_QUERY_ENDPOINT = "/mpesa/stkpushquery/v1/query"

    @classmethod
    async def get_access_token(cls) -> str:
        """Fetch OAuth access token with strict production handling."""
        url = f"{cls.BASE_URL}{cls.OAUTH_ENDPOINT}"
        credentials = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        logger.info(f"M-Pesa OAuth: REQUEST {url}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Basic {encoded_credentials}"},
                )
                
                if response.status_code != 200:
                    logger.error(f"M-Pesa OAuth: FAILED Status={response.status_code} Body={response.text}")
                    raise Exception(f"Safaricom OAuth Error: {response.text}")
                
                data = response.json()
                logger.info("M-Pesa OAuth: SUCCESS Token generated.")
                return data["access_token"]
                
            except Exception as e:
                logger.error(f"M-Pesa OAuth: UNEXPECTED ERROR {str(e)}")
                raise Exception(f"Internal OAuth Failure: {str(e)}")

    @classmethod
    def generate_password(cls, timestamp: str) -> str:
        """Generate STK push password using ShortCode, Passkey, and Timestamp."""
        raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        return base64.b64encode(raw.encode()).decode()

    @classmethod
    def normalize_phone(cls, phone: str) -> str:
        """Strictly normalize phone number to 254XXXXXXXXX format."""
        clean = re.sub(r"\D", "", phone)
        if clean.startswith("0"):
            clean = "254" + clean[1:]
        elif (clean.startswith("7") or clean.startswith("1")) and len(clean) == 9:
            clean = "254" + clean
        elif clean.startswith("254") and len(clean) == 12:
            pass
        elif clean.startswith("+254"):
            clean = clean[1:]
        
        if len(clean) != 12 or not clean.startswith("254"):
            logger.warning(f"Phone Normalization: Result {clean} may be invalid for input {phone}")
        return clean

    @classmethod
    async def initiate_stk_push(
        cls,
        phone_number: str,
        amount: float,
        account_ref: str,
        desc: str,
        callback_url: str = None
    ) -> dict:
        """Initiate STK Push with strict production compliance and robust logging."""
        try:
            token = await cls.get_access_token()
        except Exception as e:
            return {"ResponseCode": "1", "errorMessage": str(e)}

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        password = cls.generate_password(timestamp)
        phone = cls.normalize_phone(phone_number)
        
        # Determine TransactionType: Default to Paybill, fallback to BuyGoods if needed
        # We'll try Paybill first as it's the most common for ShortCodes like 3538431
        t_type = "CustomerPayBillOnline"
        
        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": t_type,
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": callback_url or settings.MPESA_CALLBACK_URL,
            "AccountReference": account_ref[:12],
            "TransactionDesc": desc[:20],
        }

        url = f"{cls.BASE_URL}{cls.STK_PUSH_ENDPOINT}"
        logger.info(f"STK Push ({t_type}): REQUEST {url} PHONE={phone} AMOUNT={amount}")
        logger.info(f"STK Push ({t_type}): PAYLOAD {json.dumps({**payload, 'Password': '***'})}")

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                
                data = response.json()
                logger.info(f"STK Push ({t_type}): RESPONSE {response.status_code} BODY={response.text}")

                # Auto-retry with CustomerBuyGoodsOnline if it looks like a Till Number issue
                if response.status_code != 200 or data.get("ResponseCode") != "0":
                    err_msg = response.text.lower()
                    if "invalid" in err_msg or "shortcode" in err_msg:
                        logger.info("STK Push: Retrying with CustomerBuyGoodsOnline...")
                        payload["TransactionType"] = "CustomerBuyGoodsOnline"
                        response = await client.post(
                            url,
                            json=payload,
                            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        )
                        data = response.json()
                        logger.info(f"STK Push Retry (BuyGoods): RESPONSE {response.status_code} BODY={response.text}")

                if response.status_code == 200 and data.get("ResponseCode") == "0":
                    logger.info(f"STK Push: SUCCESS CheckoutID={data.get('CheckoutRequestID')}")
                    return data
                
                return {
                    "ResponseCode": data.get("ResponseCode", str(response.status_code)),
                    "errorMessage": data.get("errorMessage", data.get("ResponseDescription", "Safaricom API Error")),
                    "details": data
                }
                
            except Exception as e:
                logger.error(f"STK Push: API ERROR {str(e)}")
                return {"ResponseCode": "1", "errorMessage": f"Connection failed: {str(e)}"}

    @classmethod
    async def query_status(cls, checkout_id: str) -> dict:
        """Query the status of an STK push transaction."""
        try:
            token = await cls.get_access_token()
        except Exception as e:
            return {"ResponseCode": "1", "errorMessage": str(e)}

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        password = cls.generate_password(timestamp)

        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_id,
        }

        url = f"{cls.BASE_URL}{cls.STK_QUERY_ENDPOINT}"
        logger.info(f"STK Query: REQUEST {url} CheckoutID={checkout_id}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                return response.json()
            except Exception as e:
                logger.error(f"STK Query: ERROR {str(e)}")
                return {"ResponseCode": "1", "errorMessage": str(e)}

# Backward compatibility for existing code while refactoring
async def initiate_stk_push(phone_number, amount, account_reference, transaction_desc, callback_url):
    return await MpesaService.initiate_stk_push(phone_number, amount, account_reference, transaction_desc, callback_url)

async def get_mpesa_access_token():
    return await MpesaService.get_access_token()

async def query_stk_push_status(checkout_id):
    return await MpesaService.query_status(checkout_id)
