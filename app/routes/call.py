from fastapi import APIRouter, Request, HTTPException, Depends, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
from  app.helpers.config import get_settings
import logging
from typing import Optional
import secrets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBasic()
app_settings = get_settings()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Validates Basic Auth credentials.
    """
    correct_username = secrets.compare_digest(credentials.username, app_settings.API_AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, app_settings.API_AUTH_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@router.post("/call", response_class=JSONResponse)
async def initiate_call(request: Request, username: str = Depends(authenticate)) -> JSONResponse:
    """
    Initiates a call to the specified phone number using Twilio.
    
    Expects a JSON payload with the 'to_phone' field.
    Requires Basic Authentication.
    """
    try:
        TWILIO_ACCOUNT_SID = app_settings.TWILIO_ACCOUNT_SID
        TWILIO_AUTH_TOKEN = app_settings.TWILIO_AUTH_TOKEN
        TWILIO_PHONE_NUMBER = app_settings.TWILIO_PHONE_NUMBER

        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("Twilio Client initialized.")
        data = await request.json()
        to_phone: Optional[str] = data.get('to_phone')

        if not to_phone:
            logger.warning("Missing 'to_phone' in request data.")
            raise HTTPException(status_code=400, detail="Phone number ('to_phone') is required.")

        host = request.url.hostname
        if not host:
            logger.error("Unable to determine the host from the request URL.")
            raise HTTPException(status_code=500, detail="Invalid host in request URL.")

        callback_url = f'https://{host}/incoming-call'
        logger.info(f"Callback URL constructed: {callback_url}")
        logger.info(f"Authenticated user '{username}' is initiating a call from {TWILIO_PHONE_NUMBER} to {to_phone}.")

        call = twilio_client.calls.create(
            to=to_phone,
            from_=TWILIO_PHONE_NUMBER,
            url=callback_url
        )

        logger.info(f"Call initiated successfully. Call SID: {call.sid}")
        return JSONResponse({"message": "Call initiated", "call_sid": call.sid}, status_code=200)

    except HTTPException as http_exc:
        logger.warning(f"HTTP exception occurred: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Error initiating call: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@router.api_route("/incoming-call", methods=["GET", "POST"], response_class=HTMLResponse)
async def handle_incoming_call(request: Request) -> HTMLResponse:
    """
    Handles incoming Twilio calls by responding with TwiML instructions.
    Streams the call to the specified WebSocket endpoint.
    """
    try:
        response = VoiceResponse()
        response.pause(length=1)  # Adds a 1-second pause before connecting

        host = request.url.hostname
        if not host:
            logger.error("Unable to determine the host from the request URL.")
            raise HTTPException(status_code=500, detail="Invalid host in request URL.")

        stream_url = f'wss://{host}/media-stream'
        logger.info(f"Streaming call to WebSocket URL: {stream_url}")

        connect = Connect()
        connect.stream(url=stream_url)
        response.append(connect)

        logger.info("Incoming call response constructed successfully.")
        return HTMLResponse(content=str(response), media_type="application/xml")

    except HTTPException as http_exc:
        logger.warning(f"HTTP exception occurred: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Error handling incoming call: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)