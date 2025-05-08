# config.py
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import Optional, Set

print(">>> [DEBUG config.py] Top of file.") # Debug print

# Load environment variables from .env file
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    # Use override=True to ensure .env values take precedence over existing env vars if needed
    loaded = load_dotenv(dotenv_path, override=True, verbose=True)
    print(f">>> [DEBUG config.py] python-dotenv loaded: {loaded}. Path: {dotenv_path}")
    # Optionally print loaded vars from dotenv immediately
    # print(f">>> [DEBUG config.py] os.getenv('SUPABASE_URL') after load_dotenv: {os.getenv('SUPABASE_URL')}")
    # print(f">>> [DEBUG config.py] os.getenv('SUPABASE_KEY') after load_dotenv: {os.getenv('SUPABASE_KEY')[:10] if os.getenv('SUPABASE_KEY') else 'None'}...")
else:
    print(f">>> [DEBUG config.py] Warning: .env file not found at {dotenv_path}.")

class Settings(BaseSettings):
    """Application configuration settings."""
    print(">>> [DEBUG config.py] Inside Settings class definition.") # Debug print

    # --- FastAPI Specific Settings ---
    FASTAPI_HOST: str = '127.0.0.1'
    FASTAPI_PORT: int = 8001 # Keep port 8001

    # --- Supabase Configuration ---
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None # This is the ANON public key
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None # This is the secret service key
    SUPABASE_DB_CONN_STRING: Optional[str] = None

    # --- JWT Authentication Settings ---
    # Read from env, provide default if not set
    JWT_SECRET_KEY: str = 'your-super-secret-jwt-key-keep-it-safe-and-change-me'
    JWT_ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- General App Settings ---
    APP_NAME: str = "SpendLens API"
    # Read DEBUG_MODE from environment or default to True for development
    DEBUG_MODE: bool = os.environ.get('DEBUG_MODE', 'True').lower() in ('true', '1', 't')

    UPLOAD_FOLDER: str = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads_fastapi')
    ALLOWED_EXTENSIONS: Set[str] = {'csv'}

    # --- LLM Settings ---
    GOOGLE_API_KEY: Optional[str] = None # Loaded from .env by BaseSettings
    DEFAULT_LLM_CONTEXT_DAYS: int = 730 # Default to 2 years of context for LLM Q&A

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

print(">>> [DEBUG config.py] Attempting to instantiate Settings()...") # Debug print
settings = Settings()
print(">>> [DEBUG config.py] Settings() instantiated.") # Debug print

# --- ADDED: Print loaded values immediately after instantiation ---
print("\n--- [DEBUG config.py] Values loaded into settings object ---")
print(f"  settings.SUPABASE_URL: {settings.SUPABASE_URL}")
print(f"  settings.SUPABASE_KEY (anon): {settings.SUPABASE_KEY[:10] if settings.SUPABASE_KEY else 'None'}...") # Print start only
print(f"  settings.FASTAPI_PORT: {settings.FASTAPI_PORT}")
print("--- End Debug Print ---\n")
# --- END ADDED ---


# Optional: Print loaded settings if running directly (useful for debugging config)
if __name__ == "__main__":
    print("\n--- Configuration Settings Loaded (if __name__ == '__main__') ---")
    print(f"  FastAPI Host: {settings.FASTAPI_HOST}")
    print(f"  FastAPI Port: {settings.FASTAPI_PORT}")
    print(f"  Debug Mode: {settings.DEBUG_MODE}")
    print(f"  Supabase URL: {'Set' if settings.SUPABASE_URL else 'Not Set'}")
    print(f"  Supabase Key: {'Set' if settings.SUPABASE_KEY else 'Not Set'}")
    print(f"  Supabase Service Role Key: {'Set' if settings.SUPABASE_SERVICE_ROLE_KEY else 'Not Set'}")
    print(f"  Supabase DB Connection String: {'Set' if settings.SUPABASE_DB_CONN_STRING else 'Not Set'}")
    print(f"  JWT Secret Key: {'Set (ends with ...' + settings.JWT_SECRET_KEY[-4:] + ')' if settings.JWT_SECRET_KEY and 'your-super-secret' not in settings.JWT_SECRET_KEY else 'Default or Not Set'}")
    print(f"  Google API Key: {'Set' if settings.GOOGLE_API_KEY else 'Not Set'}")
    print("--- End Configuration ---")
