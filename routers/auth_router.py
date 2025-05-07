# routers/auth_router.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from supabase import Client as SupabaseClient

from models_pydantic import TokenPydantic, UserCreatePydantic, UserPydantic
import database_supabase as db_supabase
# Removed: from api_main import supabase

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}},
)

log = logging.getLogger('auth_router')
if not log.handlers and not (log.parent and log.parent.handlers):
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)
    log.propagate = False

# --- Dependency to get Supabase client ---
def get_supabase_client(request: Request) -> SupabaseClient:
    """Dependency to get the Supabase client from app.state."""
    if not hasattr(request.app.state, 'supabase_client') or request.app.state.supabase_client is None:
        log.error("Supabase client not found in app.state. Ensure it's initialized at startup.")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service is not configured.")
    return request.app.state.supabase_client

@router.post("/token", response_model=TokenPydantic)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    supabase: SupabaseClient = Depends(get_supabase_client) # Inject Supabase client
):
    log.info(f"Token request for username (email): {form_data.username}")
    try:
        res = supabase.auth.sign_in_with_password({"email": form_data.username, "password": form_data.password})
        if res.session and res.session.access_token and res.user:
            log.info(f"Supabase login successful for user: {res.user.id}")
            db_supabase.create_user_profile(str(res.user.id), str(res.user.email))
            return TokenPydantic(
                access_token=res.session.access_token, token_type="bearer",
                refresh_token=res.session.refresh_token,
                user=UserPydantic(id=str(res.user.id), email=str(res.user.email))
            )
        else:
            error_msg = res.error.message if res.error else "Unknown Supabase login error"
            log.warning(f"Supabase login failed for {form_data.username}: {error_msg}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Incorrect email or password: {error_msg}", headers={"WWW-Authenticate": "Bearer"})
    except Exception as e:
        log.error(f"Error during Supabase sign-in for {form_data.username}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during login.")

@router.post("/register", response_model=UserPydantic, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_create: UserCreatePydantic,
    supabase: SupabaseClient = Depends(get_supabase_client) # Inject Supabase client
):
    log.info(f"Registration attempt for email: {user_create.email}")
    try:
        res = supabase.auth.sign_up({"email": user_create.email, "password": user_create.password})
        if res.user and res.user.id:
            log.info(f"Supabase registration successful for user: {res.user.id}. Email verification may be required.")
            profile = db_supabase.create_user_profile(str(res.user.id), str(res.user.email))
            if profile: return UserPydantic(id=str(profile.id), email=profile.email, username=profile.username)
            else: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user profile after registration.")
        elif res.error:
            log.warning(f"Supabase registration failed for {user_create.email}: {res.error.message}")
            if "already registered" in res.error.message.lower(): raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=res.error.message)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.error.message)
        else:
            log.warning(f"Supabase registration for {user_create.email} resulted in an unexpected state.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Registration initiated, or an unknown issue occurred.")
    except Exception as e:
        log.error(f"Error during Supabase sign-up for {user_create.email}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during registration.")
