# routers/auth_router.py
import logging
from typing import Annotated # Use Annotated for Depends
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from supabase import Client as SupabaseClient
from gotrue.errors import AuthApiError # Import specific Supabase error

# Project specific imports
from models_pydantic import TokenPydantic, UserCreatePydantic, UserPydantic
import database_supabase as db_supabase
# Import the dependency to get the current user based on JWT
from auth.dependencies import get_current_supabase_user # Assuming dependencies.py is in auth folder

router = APIRouter(
    prefix="/api/v1/auth", # Prefix for auth related routes
    tags=["Authentication"],
    responses={404: {"description": "Not found"}},
)

log = logging.getLogger('auth_router')
if not log.handlers and not (hasattr(log.parent, 'handlers') and log.parent.handlers):
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(module)s:%(funcName)s:%(lineno)d] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.propagate = False

# --- Dependency to get Supabase client ---
# This dependency injects the Supabase client stored in app.state
def get_supabase_client(request: Request) -> SupabaseClient:
    """Dependency to get the Supabase client from app.state."""
    supabase_client = getattr(request.app.state, 'supabase_client', None)
    if supabase_client is None:
        log.error("Supabase client not found in app.state. Ensure it's initialized at startup in api_main.py.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service is not configured.")
    return supabase_client

@router.post("/token", response_model=TokenPydantic)
async def login_for_access_token(
    # Use Annotated for dependency injection with type hints
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    supabase: Annotated[SupabaseClient, Depends(get_supabase_client)] # Inject Supabase client
):
    """Handles user login with email and password, returns JWT."""
    log.info(f"Token request for username (email): {form_data.username}")
    try:
        # Attempt sign-in using Supabase Auth
        res = supabase.auth.sign_in_with_password({"email": form_data.username, "password": form_data.password})

        # Check for successful response with session and user data
        if res.session and res.session.access_token and res.user and res.user.id and res.user.email:
            log.info(f"Supabase login successful for user: {res.user.id}")
            # Ensure user profile exists in our database
            profile = db_supabase.create_user_profile(str(res.user.id), str(res.user.email))
            if not profile: # If creation failed or didn't return, try fetching
                 profile = db_supabase.get_user_profile_by_id(str(res.user.id))

            if not profile: # Still no profile? Problem during creation/fetch
                 log.error(f"Failed to create/retrieve profile for user {res.user.id} after successful Supabase login.")
                 # Consider whether to fail login or proceed without full profile data
                 # Returning error for now to highlight the issue
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login succeeded but user profile sync failed.")

            # Prepare user data for the response token
            user_for_token = UserPydantic(
                id=str(res.user.id),
                email=str(res.user.email),
                username=profile.username # Include username from our profile table
            )
            # Return the token details and user info
            return TokenPydantic(
                access_token=res.session.access_token,
                token_type="bearer",
                refresh_token=res.session.refresh_token,
                user=user_for_token
            )
        elif res.error: # Handle specific Supabase errors if provided
            error_msg = res.error.message
            log.warning(f"Supabase login failed for {form_data.username}: {error_msg}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Incorrect email or password.", headers={"WWW-Authenticate": "Bearer"})
        else: # Handle unexpected successful response structure
             log.error(f"Supabase login for {form_data.username} returned unexpected response structure.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed due to unexpected auth service response.")

    except AuthApiError as e: # Catch specific Supabase API errors
         log.warning(f"Supabase AuthApiError during sign-in for {form_data.username}: {e.message}")
         # Provide specific messages for common errors
         if "invalid login credentials" in e.message.lower():
             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login credentials.", headers={"WWW-Authenticate": "Bearer"})
         elif "email not confirmed" in e.message.lower():
              raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email not confirmed. Please check your inbox.", headers={"WWW-Authenticate": "Bearer"})
         else:
              raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Authentication error: {e.message}", headers={"WWW-Authenticate": "Bearer"})
    except HTTPException: # Re-raise exceptions we threw intentionally
        raise
    except Exception as e: # Catch any other unexpected errors
        log.error(f"Unexpected error during Supabase sign-in for {form_data.username}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during login.")

@router.post("/register", response_model=UserPydantic, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_create: UserCreatePydantic,
    supabase: Annotated[SupabaseClient, Depends(get_supabase_client)] # Inject Supabase client
):
    """Handles new user registration."""
    log.info(f"Registration attempt for email: {user_create.email}")
    try:
        # Attempt sign-up using Supabase Auth
        res = supabase.auth.sign_up({"email": user_create.email, "password": user_create.password})

        # Check for successful user creation
        if res.user and res.user.id and res.user.email:
            log.info(f"Supabase registration successful for user: {res.user.id}. Email verification may be required.")
            # Create corresponding profile in our database
            profile = db_supabase.create_user_profile(str(res.user.id), str(res.user.email))
            if profile:
                # Return created user details
                return UserPydantic(id=str(profile.id), email=profile.email, username=profile.username)
            else: # Handle failure to create profile after successful Supabase signup
                log.error(f"Failed to create local profile for newly registered Supabase user {res.user.id}.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration succeeded but user profile creation failed.")
        elif res.error: # Handle Supabase signup errors
            log.warning(f"Supabase registration failed for {user_create.email}: {res.error.message}")
            # Check for specific common errors
            if "already registered" in res.error.message.lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=res.error.message)
            # Handle other Supabase errors
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.error.message)
        else: # Handle unexpected response structure from Supabase
            log.warning(f"Supabase registration for {user_create.email} resulted in an unexpected state (no user, no error).")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Registration process yielded an unexpected result.")

    except AuthApiError as e: # Catch specific Supabase API errors during signup
        log.warning(f"Supabase AuthApiError during sign-up for {user_create.email}: {e.message}")
        if "user already registered" in e.message.lower():
             raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
        else:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Registration error: {e.message}")
    except HTTPException: # Re-raise exceptions we threw intentionally
        raise
    except Exception as e: # Catch any other unexpected errors
        log.error(f"Unexpected error during Supabase sign-up for {user_create.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred during registration.")


# --- NEW ENDPOINT ---
@router.get("/users/me", response_model=UserPydantic)
async def read_users_me(
    # Use the dependency from auth.dependencies to get the user from the token
    current_user: Annotated[UserPydantic, Depends(get_current_supabase_user)]
):
    """
    Returns the details of the currently authenticated user based on the JWT token.
    Used by the frontend to verify a token and get user info.
    """
    # The get_current_supabase_user dependency already validates the token
    # and fetches/creates the user profile. We just need to return it.
    # The dependency returns a UserPydantic model directly.
    log.info(f"Returning user details for user ID: {current_user.id} via /users/me")
    return current_user
# --- END NEW ENDPOINT ---

