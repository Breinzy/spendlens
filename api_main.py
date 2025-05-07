# api_main.py
import logging
import os
from typing import Optional
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client as SupabaseClient # For type hinting

# --- Project Specific Imports ---
from config import settings
# Routers
from routers import auth_router, transactions_router, insights_router
# Auth utilities (if needed directly here, though mostly used in routers)
# from auth.dependencies import get_current_supabase_user

# --- Supabase Client Initialization ---
supabase_url: Optional[str] = settings.SUPABASE_URL
supabase_key: Optional[str] = settings.SUPABASE_KEY

# This global supabase client can be problematic for testing and scaling.
# Consider using FastAPI's dependency injection or app.state for better management.
# However, for direct import by routers as done in this iteration, it needs to be here.
if not supabase_url or not supabase_key:
    logging.critical("Supabase URL or Key not found in settings. FastAPI app cannot start properly.")
    supabase: Optional[SupabaseClient] = None
else:
    try:
        supabase: Optional[SupabaseClient] = create_client(supabase_url, supabase_key)
        logging.info("Supabase client initialized successfully (using anon key).")
    except Exception as e:
        logging.critical(f"Failed to initialize Supabase client: {e}", exc_info=True)
        supabase = None


# --- FastAPI App Initialization ---
app = FastAPI(
    title=settings.APP_NAME,
    description="API for SpendLens, your AI-powered financial assistant.",
    version="2.0.0"
)

# --- Configure Logging for FastAPI ---
log = logging.getLogger('fastapi_app')
log.setLevel(logging.INFO if not settings.DEBUG_MODE else logging.DEBUG)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

# --- CORS Middleware ---
origins = [
    "http://localhost", "http://localhost:3000", "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Include API Routers ---
app.include_router(auth_router.router)
app.include_router(transactions_router.router)
app.include_router(insights_router.router)


# Simple root endpoint
@app.get("/", tags=["General"])
async def read_root():
    log.info("Root endpoint '/' accessed.")
    return {"message": f"Welcome to {settings.APP_NAME} - V2 API"}


# --- Main Execution (for local development) ---
if __name__ == "__main__":
    log.info(f"Starting SpendLens FastAPI server (Debug: {settings.DEBUG_MODE})...")
    # Ensure the Uvicorn reload directory points to where your api_main.py and routers are
    # if your project structure is flat, "." might be okay.
    # If api_main.py is in a subdirectory like 'app', use 'app.api_main:app'
    # and ensure Uvicorn watches the correct directories.
    uvicorn.run(
        "api_main:app",  # <<<< IMPORTANT: Changed from "main_fastapi:app"
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
        reload=settings.DEBUG_MODE,
        reload_dirs=["./", "./routers", "./auth"] # Add directories to watch for changes
    )
