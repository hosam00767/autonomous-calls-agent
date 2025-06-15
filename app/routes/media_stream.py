import json
import base64
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState  
import websockets
import os
import logging
from typing import Optional
from  app.helpers.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load configuration paths
BASE_DIR = os.path.dirname(__file__)
SESSION_FILE_PATH = os.path.join(BASE_DIR, "..", "config", "gpt_audio_session_template.json")
INSTRUCTION_FILE_PATH  = os.path.join(BASE_DIR, "..", "config", "system_instructions.txt")

# Constants
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created']

SHOW_TIMING_MATH = False
app_settings = get_settings()

router = APIRouter()
@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """
    Manages the WebSocket connection between Twilio and the GPT-powered service.
    Streams audio data to and from the GPT service.
    """
    app_settings = get_settings()
    await websocket.accept()
    logger.info("Client connected to /media-stream.")
   
    azure_ws_url = (
        f"wss://{app_settings.AZURE_OPENAI_ENDPOINT}/openai/realtime"
        f"?api-version={app_settings.AZURE_OPENAI_API_VERSION}"
        f"&deployment={app_settings.AZURE_OPENAI_DEPLOYMENT_NAME}"
        f"&api-key={app_settings.AZURE_OPENAI_API_KEY}"
    )

    shutdown_event = asyncio.Event()  # Event to signal shutdown

    try:
        async with websockets.connect(azure_ws_url, ssl=True) as azure_ws:
            logger.info("Connected to Azure OpenAI WebSocket.")
            await initialize_session(azure_ws)
            # Initialize state variables
            stream_sid: Optional[str] = None
            latest_media_timestamp: int = 0
            last_assistant_item: Optional[str] = None
            mark_queue: list = []
            response_start_timestamp_twilio: Optional[int] = None
            conversation_transcript = ""


            async def receive_from_twilio():
                nonlocal stream_sid, latest_media_timestamp, response_start_timestamp_twilio, conversation_transcript
                logger.info("Started receiving from Twilio.")
                try:
                    while not shutdown_event.is_set():
                        try:
                            message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue  # Periodically check for shutdown
                        data = json.loads(message)
                        event_type = data.get('event')

                        if event_type == 'media' and azure_ws.open:
                            latest_media_timestamp = int(data['media']['timestamp'])
                            audio_payload = data['media']['payload']
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": audio_payload
                            }
                            await azure_ws.send(json.dumps(audio_append))
                            logger.debug("Appended audio buffer to Azure.")

                        elif event_type == 'start':
                            stream_sid = data['start']['streamSid']
                            logger.info(f"Incoming stream started: {stream_sid}")
                            response_start_timestamp_twilio = None

                        elif event_type == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)
                                logger.debug("Processed a mark event from Twilio.")

                        elif event_type == 'hangup':
                            logger.info("Received hangup event from Twilio.")
                            shutdown_event.set()

                except WebSocketDisconnect:
                    logger.warning("Twilio disconnected from /media-stream.")
                    shutdown_event.set()
                except Exception as e:
                    logger.error(f"Error in receive_from_twilio: {e}", exc_info=True)
                    shutdown_event.set()

            async def send_to_twilio():
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio, conversation_transcript
                logger.info("Started sending to Twilio.")
                try:
                    async for openai_message in azure_ws:
                        if shutdown_event.is_set():
                            logger.info("Shutdown event detected. Stopping send_to_twilio.")
                            break
                        try:
                            response = json.loads(openai_message)

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode OpenAI message: {e}")
                            continue

                        event_type = response.get('type')

                        if event_type in LOG_EVENT_TYPES:
                            logger.info(f"Received event from Azure: {event_type}")

                        if  event_type ==  "response.content_part.done":
                                logger.info(f"AGENT TRANSCRIPT: {response['content']['transcript']}")
                                conversation_transcript += f"AGENT TRANSCRIPT: {response['content']['transcript']}" + "\n"
                        if event_type == 'response.audio.delta' and 'delta' in response:
                            try:
                                decoded_audio = base64.b64decode(response['delta'])
                                audio_payload = base64.b64encode(decoded_audio).decode('utf-8')
                            except (base64.binascii.Error, TypeError) as e:
                                logger.error(f"Error decoding audio delta: {e}")
                                continue  # Skip this message

                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            try:
                                await websocket.send_json(audio_delta)
                                logger.debug("Sent audio delta to Twilio.")
                            except WebSocketDisconnect:
                                logger.warning("Twilio WebSocket disconnected while sending audio_delta.")
                                shutdown_event.set()
                                break
                            except Exception as e:
                                logger.error(f"Error sending audio_delta to Twilio: {e}", exc_info=True)
                                shutdown_event.set()
                                break

                            if response_start_timestamp_twilio is None:
                                response_start_timestamp_twilio = latest_media_timestamp
                                if SHOW_TIMING_MATH:
                                    logger.info(f"Start timestamp set: {response_start_timestamp_twilio}ms")

                            if response.get('item_id'):
                                last_assistant_item = response['item_id']
                                logger.debug(f"Updated last_assistant_item: {last_assistant_item}")

                            await send_mark(websocket, stream_sid)

                        elif event_type == 'input_audio_buffer.speech_started':
                            logger.info("Speech started detected from caller.")
                            if last_assistant_item:
                                logger.info(f"Interrupting response with ID: {last_assistant_item}")
                                await handle_speech_started_event()

                        # Handle Customer Transcript
                        elif event_type == 'conversation.item.input_audio_transcription.completed':
                            customer_transcript = response['transcript']
                            conversation_transcript += f"CUSTOMER TRANSCRIPT: {customer_transcript}" + "\n"
                            logger.info(f"CUSTOMER TRANSCRIPT: {customer_transcript}")

                        elif event_type == "response.function_call_arguments.done":
                            function_name = response.get('name')
                            if function_name == "hangup_call":
                                args = json.loads(response.get('arguments', '{}'))
                                logger.info(f"Function call 'hangup_call' with args: {args}")
                                print(conversation_transcript)
                                shutdown_event.set()
                        
                except websockets.exceptions.ConnectionClosed as e:
                    logger.error(f"Azure WebSocket connection closed: {e}")
                    shutdown_event.set()
                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}", exc_info=True)
                    shutdown_event.set()

            async def handle_speech_started_event():
                nonlocal response_start_timestamp_twilio, last_assistant_item
                logger.info("Handling speech started event from caller.")
                if mark_queue and response_start_timestamp_twilio is not None:
                    elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                    if SHOW_TIMING_MATH:
                        logger.info(f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms")

                    if last_assistant_item:
                        if SHOW_TIMING_MATH:
                            logger.info(f"Truncating item ID: {last_assistant_item} at {elapsed_time}ms")

                        truncate_event = {
                            "type": "conversation.item.truncate",
                            "item_id": last_assistant_item,
                            "content_index": 0,
                            "audio_end_ms": elapsed_time
                        }
                        try:
                            await azure_ws.send(json.dumps(truncate_event))
                            logger.debug("Sent truncate_event to Azure.")
                        except Exception as e:
                            logger.error(f"Error sending truncate_event to Azure: {e}", exc_info=True)

                    try:
                        clear_event = {
                            "event": "clear",
                            "streamSid": stream_sid
                        }
                        await websocket.send_json(clear_event)
                        logger.debug("Sent clear event to Twilio.")
                    except WebSocketDisconnect:
                        logger.warning("Twilio WebSocket disconnected while sending clear event.")
                    except Exception as e:
                        logger.error(f"Error sending clear event to Twilio: {e}", exc_info=True)

                    mark_queue.clear()
                    last_assistant_item = None
                    response_start_timestamp_twilio = None
                    logger.info("Cleared mark queue and reset timestamps.")

            async def send_mark(connection: WebSocket, stream_sid: str):
                if stream_sid:
                    mark_event = {
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "responsePart"}
                    }
                    try:
                        await connection.send_json(mark_event)
                        mark_queue.append('responsePart')
                        logger.debug("Sent mark event to Twilio.")
                    except WebSocketDisconnect:
                        logger.warning("Twilio WebSocket disconnected while sending mark event.")
                        shutdown_event.set()
                    except Exception as e:
                        logger.error(f"Error sending mark event to Twilio: {e}", exc_info=True)
                        shutdown_event.set()

            # Create tasks for receiving and sending
            receive_task = asyncio.create_task(receive_from_twilio(), name="receive_from_twilio")
            send_task = asyncio.create_task(send_to_twilio(), name="send_to_twilio")

            logger.info("WebSocket handler tasks started.")
            # Wait for shutdown_event to be set
            await shutdown_event.wait()
            logger.info("Shutdown event triggered. Closing connections...")

            # Cancel tasks if they're still running
            for task in [receive_task, send_task]:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                        logger.info(f"{task.get_name()} has been cancelled.")
                    except asyncio.CancelledError:
                        logger.info(f"{task.get_name()} was successfully cancelled.")
                    except Exception as e:
                        logger.error(f"Error cancelling {task.get_name()}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
    finally:
        try:
            # Check the WebSocket state before attempting to close
            if websocket.application_state != WebSocketState.DISCONNECTED:
                await websocket.close()
                logger.info("Twilio WebSocket connection closed.")

            if not azure_ws.closed:
                end_call(azure_ws)
                await azure_ws.close()
                logger.info("Azure WebSocket connection closed.")

        except Exception as e:
            logger.error(f"Error closing Twilio WebSocket: {e}", exc_info=True)
        finally:
            logger.info("WebSocket connection closed.")
            
async def end_call(azure_ws):
    """
    Sends the initial message to start the conversation with the GPT service.
    """
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "close the call now with the customer"
                }
            ]
        }
    }
    await azure_ws.send(json.dumps(initial_conversation_item))

async def initialize_session(azure_ws):
    """
    Initializes the session with the GPT 4o audio service by sending session configurations.
    """
    try:
            # Load session configuration
            with open(SESSION_FILE_PATH, "r", encoding="utf-8") as file:
                session_config = json.load(file)
            logger.info("GPT session file loaded successfully.")

            # Load system instructions
            with open(INSTRUCTION_FILE_PATH, 'r', encoding='utf-8') as file:
                    instructions = file.read()
            logger.info("System instructions file loaded successfully.")

            # Update session configuration
            session = {"type": "session.update", "session": session_config}
            session["session"].update({"temperature": app_settings.GPT_AUDIO_TEMPRATURE, "instructions": instructions, "voice": app_settings.GPT_AUDIO_VOICE_NAME})
            session["session"]["turn_detection"].update({ "threshold": app_settings.GPT_AUDIO_THRESHOLD,"silence_duration_ms": app_settings.GPT_AUDIO_SILENCE_DURATION_MS,"prefix_padding_ms": app_settings.GPT_AUDIO_PREFIX_PADDING_MS})

            # Send session configuration to Azure
            await azure_ws.send(json.dumps(session))
            logger.info("Session update sent to Azure.")
            
            # Start conversation
            await azure_ws.send(json.dumps({"type": "response.create"}))
            logger.info("conversation started.")

    except FileNotFoundError as e:
        logger.error(f"Session configuration or System instruction file not found: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding session configuration JSON: {e}")
    except Exception as e:
        logger.error(f"Error initializing session: {e}", exc_info=True)
        
