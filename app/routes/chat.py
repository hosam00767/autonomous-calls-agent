from fastapi import FastAPI, HTTPException, Depends, status, APIRouter
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import requests
from typing import List
from  app.helpers.config import get_settings
import secrets
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

# Load environment variables
logger = logging.getLogger(__name__)

router = APIRouter()
app_settings = get_settings()

# Basic Authentication setup
security = HTTPBasic()

# Validate Basic Auth credentials
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

# Request model for user input
class ChatRequest(BaseModel):
    last_message: str  # The latest user message,
    masseges_history: str  # The last message from the bot

    

def send_request_to_openai(payload: dict) -> dict:
    """
    Sends a request to Azure OpenAI using the requests library.
    This function runs in a separate thread to avoid blocking the event loop.
    """
    url = f"https://{app_settings.AZURE_OPENAI_ENDPOINT}/openai/deployments/{app_settings.AZURE_OPENAI_CHAT_DEPLOYMENT_NAME}/chat/completions?api-version=2024-08-01-preview"
    headers = {
        "Content-Type": "application/json",
            "api-key": app_settings.AZURE_OPENAI_API_KEY,
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        logger.error(f"Azure OpenAI API error: {response.text}")
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()

@router.post("/chat", response_class=JSONResponse)
async def chat_with_gpt(request: ChatRequest, username: str = Depends(authenticate)) -> JSONResponse:
    """
    Handles chat requests to Azure OpenAI and returns the response.
    Requires Basic Authentication.
    """
    try:
        # Read JSON payload
        logger.info("Last message is "+request.last_message) 
        logger.info("Messages_history "+request.masseges_history) 

        prompt = request.last_message
        if not prompt or prompt == "":
            logger.warning("Missing 'prompt' in request data.")
            raise HTTPException(status_code=400, detail="Field 'prompt' is required.")

        # Construct API request payload
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }
        logger.info(f"User '{username}' is sending a request to Azure OpenAI.")

        # Run the request in a separate thread to avoid blocking FastAPI's async execution
        response_data = await asyncio.to_thread(send_request_to_openai, payload)
        output = response_data["choices"][0]["message"]["content"]
        logger.info("Azure OpenAI response received successfully.")
        return JSONResponse(content=output, status_code=200)

    except HTTPException as http_exc:
        logger.warning(f"HTTP exception occurred: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)