import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.routes import call, media_stream, chat 

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Dentinnova Agent")

app = FastAPI()

# Include Routers
app.include_router(call.router)
app.include_router(media_stream.router)
app.include_router(chat.router)

@app.get("/", response_class=JSONResponse)
async def index_page() -> JSONResponse:
    """
    Root endpoint to verify that the Agent is running
    
    Returns:
        JSONResponse: A simple JSON message.
    """
    logger.info("Root endpoint '/' accessed.")
    return JSONResponse({"message": "Dentinnova calls agent is running!"}, status_code=200)
