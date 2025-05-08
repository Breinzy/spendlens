# auth/dependencies.py
import logging
from typing import Dict, Any, Optional, Annotated # Added Annotated
# import httpx # No longer needed for JWKS fetch here
# from cachetools import TTLCache # No longer needed for JWKS fetch here
from fastapi import Depends, HTTPException, status, Request # Request needed for app.state
from fastapi.security import OAuth2PasswordBearer
# from jose import JWTError, jwt # No longer needed for manual decoding
# from jose.exceptions import JOSEError # No longer needed
from supabase import Client as SupabaseClient # Import Supabase client
from gotrue.errors import AuthApiError # Import Supabase auth error

# Project specific imports
from config import settings
import database_supabase as db_supabase
from models_pydantic import UserPydantic

# Configure logging
log = logging.getLogger('auth_dependencies')
log.setLevel(logging.INFO if not settings.DEBUG_MODE else logging.DEBUG)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.propagate = False

# OAuth2 scheme pointing to the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token") # Path relative to frontend

# --- JWKS Fetching Removed ---
# We will now rely on supabase-py client's internal handling

# --- Dependency to get Supabase client from app.state ---
# (Copied from auth_router.py - ensure it's consistent or move to a shared location)
def get_supabase_client(request: Request) -> SupabaseClient:
    """Dependency to get the Supabase client from app.state."""
    supabase_client = getattr(request.app.state, 'supabase_client', None)
    if supabase_client is None:
        log.error("Supabase client not found in app.state. Ensure it's initialized at startup in api_main.py.")
        # Use 503 Service Unavailable as the auth service depends on this client
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Authentication service client not available.")
    return supabase_client

# --- Rewritten Dependency using supabase.auth.get_user ---
async def get_current_supabase_user(
    # Use Annotated for modern dependency injection syntax
    token: Annotated[str, Depends(oauth2_scheme)],
    supabase: Annotated[SupabaseClient, Depends(get_supabase_client)] # Inject the client
) -> UserPydantic:
    """
    Dependency function to validate the JWT token using supabase.auth.get_user()
    and return the corresponding UserPydantic object from our database.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    log.debug("Attempting token validation via supabase.auth.get_user...")
    try:
        # Use the injected Supabase client to validate the token
        # This method handles JWKS fetching and validation internally
        auth_response = supabase.auth.get_user(token)
        supabase_user = auth_response.user

        # Check if user object and essential details are present
        if not supabase_user or not supabase_user.id or not supabase_user.email:
            log.warning("supabase.auth.get_user did not return a valid user object.")
            raise credentials_exception

        # --- User Profile Sync (Same as before) ---
        user_id = str(supabase_user.id)
        user_email = str(supabase_user.email)

        user_profile = db_supabase.get_user_profile_by_id(user_id)
        if user_profile is None:
            log.info(f"No local profile for valid Supabase user {user_id}. Creating one.")
            user_profile = db_supabase.create_user_profile(user_id, user_email)
            if user_profile is None:
                log.error(f"Failed to create local profile for valid Supabase user {user_id}.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="User profile synchronization failed after authentication.")

        # --- Success ---
        log.info(f"User {user_profile.username} (ID: {user_profile.id}) authenticated successfully via supabase.auth.get_user.")
        return UserPydantic(id=user_profile.id, email=user_profile.email, username=user_profile.username)

    # --- Error Handling ---
    except AuthApiError as e:
        # Catch specific errors from supabase-py auth methods
        log.warning(f"Supabase AuthApiError during token validation: {e.message} (Status: {e.status})")
        # Map common Supabase errors to 401
        if e.status == 401 or e.status == 403 or "invalid" in e.message.lower() or "expired" in e.message.lower():
             raise credentials_exception from e
        else: # Treat other Supabase errors as internal server errors for now
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                 detail=f"Authentication service error: {e.message}") from e
    except HTTPException as e: # Re-raise HTTPExceptions (e.g., from get_supabase_client)
        log.warning(f"HTTPException during dependency execution: {e.status_code} - {e.detail}")
        raise e
    except Exception as e: # Catch any other unexpected errors
        log.error(f"Unexpected error during token validation via supabase.auth.get_user: {str(e)}", exc_info=True)
        raise credentials_exception from e

