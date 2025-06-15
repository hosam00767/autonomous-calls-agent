from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    # Twilio
    TWILIO_ACCOUNT_SID : str 
    TWILIO_AUTH_TOKEN : str 
    TWILIO_PHONE_NUMBER : str 
    # Azure OpenAI
    AZURE_OPENAI_API_KEY : str 
    AZURE_OPENAI_ENDPOINT : str 
    AZURE_OPENAI_DEPLOYMENT_NAME : str 
    AZURE_OPENAI_API_VERSION : str 
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: str
    # GPT Audio
    GPT_AUDIO_TEMPRATURE: float  
    GPT_AUDIO_THRESHOLD: float  
    GPT_AUDIO_MAX_TOKEN: int  
    GPT_AUDIO_SILENCE_DURATION_MS: int  
    GPT_AUDIO_PREFIX_PADDING_MS: int  
    GPT_AUDIO_VOICE_NAME: str  

    # API Auth
    API_AUTH_USERNAME : str
    API_AUTH_PASSWORD : str
    
    class Config:
        env_file = ".env"

def get_settings():
    return Settings()

    
    
    
