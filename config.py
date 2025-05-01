# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file (optional but good practice)
load_dotenv()

class Config:
    """Base configuration settings for the Flask app."""

    # --- Flask Specific Settings ---

    # Secret key for session management, CSRF protection, etc.
    # IMPORTANT: Keep this secret in production! Generate a random key.
    # You can generate one using: python -c 'import secrets; print(secrets.token_hex(16))'
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'a-default-fallback-secret-key-for-dev'

    # Debug mode (should be False in production)
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']

    # Upload folder for CSV files
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')

    # Allowed file extensions for uploads
    ALLOWED_EXTENSIONS = {'csv'}

    # --- Application Specific Settings (Add more as needed) ---

    # Database configuration (already defined in database.py, but could be centralized here)
    # DATABASE_NAME = 'spendlens.db'

    # LLM API Key (handled by llm_service.py using dotenv, but could be referenced here too)
    # GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

    # Network settings for Flask development server
    HOST = os.environ.get('FLASK_HOST', '127.0.0.1')
    PORT = int(os.environ.get('FLASK_PORT', 5001))

    # You can add other configuration variables here
    # For example:
    # DEFAULT_TRANSACTION_DATE_RANGE_YEARS = 2

# --- You could define other configurations like ProductionConfig, DevelopmentConfig ---
# class ProductionConfig(Config):
#     DEBUG = False
#     SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') # Ensure this is set securely in production

# class DevelopmentConfig(Config):
#     DEBUG = True

