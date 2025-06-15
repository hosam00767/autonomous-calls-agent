# autonmous-calls-agent

This project is a FastAPI-based application that integrates Twilio's telephony services with Azure's GPT-4 OpenAI to create an AI-powered call center agent. The AI agent can initiate and handle calls to call centers providing technical support and Marketing calls in an engaging manner.

## Features
1. **Twilio Integration:**
   - Initiates outbound calls using Twilio’s API.
   - Handles incoming calls and connects them to AI via WebSocket streams.

2. **Azure OpenAI Integration:**
   - Uses Azure's GPT-4o  real-time API.

3. **WebSocket Media Streaming:**
   - Streams audio data between Twilio and Azure GPT in real-time.
   - Manages conversational state, interruptions, and event handling.

5. **Secure and Configurable:**
   - API keys and sensitive data are configurable via environment variables.
   - Advanced encryption ensures data security.

## System Requirements
- Python 3.9
- Dependencies listed in `requirements.txt`.
- A Twilio account with a registered phone number.
- An Azure OpenAI account with GPT-4o realtime resources.
- Ngrok (or similar) for testing with a public callback URL.

## Installation
1. Clone the repository:

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   Create a `.env` file in the root directory with the following variables:
   ```env
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=your_twilio_phone_number
   AZURE_OPENAI_API_KEY=your_azure_api_key
   AZURE_OPENAI_ENDPOINT=your_azure_endpoint
   AZURE_OPENAI_DEPLOYMENT_NAME=your_azure_deployment_name
   AZURE_OPENAI_API_VERSION=2024-10-01-preview
   ```
3. Ngrok to tunnel the webserver to be accessed with Twilio (In test phase only)

         https://download.ngrok.com/windows?tab=download
      
   then open ingork and open a connection with the port 5050 or the port that your using it will provide 
   using this command in cmd 

         ngrok http 5050
      <img width="757" alt="image" src="https://github.com/user-attachments/assets/2ab52cd0-5085-4ab3-985b-9ec409ebf512" />
      
      this will give us a secure tunnel to our localhost so that we can use it to communicate with Twillio as our BaseURL


## API Endpoints
### `GET /`
- **Description:** Check the service status.
- **Response:** `{ "message": "Twilio GPT Audio Service is running!" }`

### `POST /call`
- **Description:** Initiates an outbound call.
- **Request Body:**
  ```json
  {
      "to_phone": "+1234567890"
  }
  ```
- **Response:**
  ```json
  {
      "message": "Call initiated",
      "call_sid": "CAxxxxxxxxxxxxxxxx"
  }
  ```

### `GET/POST /incoming-call`
- **Description:** Handles incoming calls and connects them to the AI media stream.

### `WEBSOCKET /media-stream`
- **Description:** Manages real-time audio streaming between Twilio and Azure GPT.

## Project Structure
```
.
├── main.py               # Main application file
├── requirements.txt      # Dependencies
├── .env                  # Environment variables (not included in repo)
├── README.md             # Project documentation
```

## Initiate Call

### we have two options to intiate the call:
1. You can intiate the call using our server end point

   POST {BaseURL}/call

   ### **Body Parameters**
   | Parameter  | Type   | Description                                                                                      
   |------------|--------|--------------------------------------------------------------------------------------------------|
   | **to_phone**     | string |  (e.g., `+971554049898`).                 |

---

2.  by directly send a request to twilio api

         https://api.twilio.com/2010-04-01/Accounts/{AccountSID}/Calls.json
- Replace `{AccountSID}` with your Twilio **Account SID**.


   ###  Authentication

   Twilio uses **Basic Authentication**. To authenticate:

   - **Username**: Your **Account SID**.
   - **Password**: Your **Auth Token**.

   The request should be made using basic HTTP authentication.

   ---

   ### Request Parameters

   The following parameters are required for the request:

   #### **Body Parameters**

   | Parameter  | Type   | Description                                                                                      |
   |------------|--------|--------------------------------------------------------------------------------------------------|
   | **To**     | string | The phone number you want to call. Must be in E.164 format (e.g., `+1234567890`).                 |
   | **From**   | string | Your Twilio phone number. Must be a valid, verified Twilio number (e.g., `+0987654321`).         |
   | **Url**    | string | The URL that will handle the callback request. {BaseURL}/incoming-call'.      |

   ### **Example Request Body**

   ```json
   {
   "To": "+1234567890",
   "From": "+0987654321",
   "Url": "{BaseURL}/incoming-call'"
   }
