# api_main.py
import logging
import os
from typing import Optional
import uvicorn

from fastapi import FastAPI, Request # Import Request for dependency injection
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client as SupabaseClient # For type hinting

# --- Project Specific Imports ---
from config import settings # Reads from config.py (including the updated port)
# Routers (ensure these imports are correct relative to api_main.py)
from routers import auth_router, transactions_router, insights_router


# --- Configure Logging ---
# Ensure logging is configured before use
log = logging.getLogger('fastapi_app') # Use a specific name
log.setLevel(logging.INFO if not settings.DEBUG_MODE else logging.DEBUG)
if not log.handlers: # Prevent adding handlers multiple times on reload
    handler = logging.StreamHandler()
    # More detailed formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
log.info("--- Starting FastAPI App Initialization ---")


# --- FastAPI App Initialization ---
# Initialize FastAPI app first
app = FastAPI(
    title=settings.APP_NAME,
    description="API for SpendLens, your AI-powered financial assistant.",
    version="2.0.1" # Increment version slightly
)
log.info("FastAPI app object initialized.")

# --- Supabase Client Initialization & App State ---
# Initialize client and store in app.state for dependency injection
supabase_url: Optional[str] = settings.SUPABASE_URL
supabase_key: Optional[str] = settings.SUPABASE_KEY
_supabase_client: Optional[SupabaseClient] = None # Temporary variable

if not supabase_url or not supabase_key:
    log.critical("Supabase URL or Key not found in settings. Auth/DB operations will likely fail.")
    app.state.supabase_client = None # Explicitly set to None
else:
    try:
        _supabase_client = create_client(supabase_url, supabase_key)
        app.state.supabase_client = _supabase_client # Store in app state
        log.info("Supabase client initialized successfully and stored in app.state.")
    except Exception as e:
        log.critical(f"Failed to initialize Supabase client: {e}", exc_info=True)
        app.state.supabase_client = None # Set to None on failure


# --- CORS Middleware ---
# Define allowed origins for Cross-Origin Resource Sharing
origins = [
    "http://localhost",        # Base domain (useful for some cases)
    "http://localhost:3000",   # Common React dev port
    "http://localhost:5173",   # Default Vite port
    "http://localhost:5174",   # Vite port if 5173 is busy
    # Add your deployed frontend URL here eventually
    # e.g., "https://your-spendlens-app.netlify.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # List of allowed origins
    allow_credentials=True, # Allow cookies
    allow_methods=["*"],    # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],    # Allow all headers
)
log.info(f"CORS middleware configured. Allowed origins: {origins}")

# --- Include API Routers ---
# Add the /api/v1 prefix here for consistency across all routers
try:
    app.include_router(auth_router.router) # Prefix is defined within auth_router.py
    app.include_router(transactions_router.router) # Prefix is defined within transactions_router.py
    app.include_router(insights_router.router, prefix="/api/v1") # Prefix added here as it was missing in the router file
    log.info("API routers included.")
except Exception as router_err:
     log.error(f"Error including routers: {router_err}", exc_info=True)
     # Consider raising the error if routers are critical
     # raise router_err


# Simple root endpoint for health check / welcome message
@app.get("/", tags=["General"])
async def read_root():
    log.info("Root endpoint '/' accessed.")
    return {"message": f"Welcome to {settings.APP_NAME} - V2 API"}


# --- Main Execution (for local development using uvicorn) ---
if __name__ == "__main__":
    log.info(f"Starting SpendLens FastAPI server (Debug: {settings.DEBUG_MODE})...")
    # Use uvicorn.run for programmatic start, reading host/port from settings
    uvicorn.run(
        "api_main:app", # Point to the FastAPI app instance in this file
        host=settings.FASTAPI_HOST, # Should be '127.0.0.1'
        port=settings.FASTAPI_PORT, # Should now be 8001 from config.py
        reload=settings.DEBUG_MODE, # Enable auto-reload if DEBUG_MODE is True
        reload_dirs=[ # Directories to watch for changes
            os.path.dirname(os.path.abspath(__file__)), # Current directory
            "routers", # Routers subdirectory
            "auth"     # Auth subdirectory (if dependencies.py is there)
            ]
    )
