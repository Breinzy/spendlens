# config.py
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import Optional, Set

# Load environment variables from .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"Successfully loaded .env file from {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}. Using default or environment-set variables.")

class Settings(BaseSettings):
    """Application configuration settings."""

    # --- FastAPI Specific Settings ---
    FASTAPI_HOST: str = '127.0.0.1'
    FASTAPI_PORT: int = 8000

    # --- Supabase Configuration ---
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_DB_CONN_STRING: Optional[str] = None

    # --- JWT Authentication Settings ---
    JWT_SECRET_KEY: str = 'your-super-secret-jwt-key-keep-it-safe-and-change-me'
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- General App Settings ---
    APP_NAME: str = "SpendLens API"
    DEBUG_MODE: bool = True

    UPLOAD_FOLDER: str = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads_fastapi')
    ALLOWED_EXTENSIONS: Set[str] = {'csv'}

    # --- LLM Settings ---
    GOOGLE_API_KEY: Optional[str] = None
    DEFAULT_LLM_CONTEXT_DAYS: int = 730 # Default to 2 years of context for LLM Q&A

    class Config:
        case_sensitive = True

settings = Settings()

if __name__ == "__main__":
    print("Configuration Settings Loaded:")
    print(f"  FastAPI Host: {settings.FASTAPI_HOST}")
    print(f"  FastAPI Port: {settings.FASTAPI_PORT}")
    print(f"  Supabase URL: {settings.SUPABASE_URL}")
    print(f"  Supabase Key (Anon/Public): {'Set' if settings.SUPABASE_KEY else 'Not Set'}")
    print(f"  Supabase Service Role Key: {'Set' if settings.SUPABASE_SERVICE_ROLE_KEY else 'Not Set'}")
    print(f"  Supabase DB Connection String: {'Set' if settings.SUPABASE_DB_CONN_STRING else 'Not Set'}")
    print(f"  JWT Secret Key: {'Set (ends with ...' + settings.JWT_SECRET_KEY[-4:] + ')' if settings.JWT_SECRET_KEY and settings.JWT_SECRET_KEY != 'your-super-secret-jwt-key-keep-it-safe-and-change-me' else 'Default or Not Set'}")
    print(f"  Access Token Expire Minutes: {settings.ACCESS_TOKEN_EXPIRE_MINUTES}")
    print(f"  Debug Mode: {settings.DEBUG_MODE}")
    print(f"  Google API Key: {'Set' if settings.GOOGLE_API_KEY else 'Not Set'}")
    print(f"  Default LLM Context Days: {settings.DEFAULT_LLM_CONTEXT_DAYS}")

    # ... (warnings from previous version) ...
