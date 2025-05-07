# auth/dependencies.py
import logging
from typing import Dict, Any, Optional
import httpx
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from jose.exceptions import JOSEError

from config import settings  # Your existing config.py
import database_supabase as db_supabase  # Your existing database_supabase.py
from models_pydantic import UserPydantic  # Your existing models_pydantic.py

log = logging.getLogger('auth_dependencies')
log.setLevel(logging.INFO if not settings.DEBUG_MODE else logging.DEBUG)
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

jwks_cache = TTLCache(maxsize=1, ttl=3600)


async def fetch_jwks() -> Dict[str, Any]:
    cached_jwks = jwks_cache.get("jwks")
    if cached_jwks:
        log.debug("Using cached JWKS.")
        return cached_jwks

    if not settings.SUPABASE_URL:
        log.error("Supabase URL not configured, cannot fetch JWKS.")
        raise HTTPException(status_code=500, detail="Authentication configuration error.")

    jwks_url = f"{settings.SUPABASE_URL.removesuffix('/')}/auth/v1/jwks"
    log.info(f"Fetching JWKS from: {jwks_url}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks = response.json()
            jwks_cache["jwks"] = jwks
            log.info("JWKS fetched and cached successfully.")
            return jwks
        except httpx.HTTPStatusError as e:
            log.error(f"HTTP error fetching JWKS: {e.response.status_code} - {e.response.text}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Could not fetch authentication keys.")
        except Exception as e:
            log.error(f"Unexpected error fetching JWKS: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Error fetching authentication keys.")


async def get_current_supabase_user(token: str = Depends(oauth2_scheme)) -> UserPydantic:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not settings.SUPABASE_URL:
        log.error("Supabase URL not configured for JWT validation.")
        raise credentials_exception

    try:
        jwks = await fetch_jwks()
        if not jwks or "keys" not in jwks:
            log.error("JWKS not available or invalid format.")
            raise credentials_exception

        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key_spec in jwks["keys"]:  # Renamed 'key' to 'key_spec' to avoid conflict
            if key_spec["kid"] == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key_spec["kty"], "kid": key_spec["kid"],
                    "use": key_spec["use"], "n": key_spec["n"], "e": key_spec["e"]
                }
                break

        if not rsa_key:
            log.warning("Unable to find appropriate key in JWKS.")
            raise credentials_exception

        payload = jwt.decode(
            token, rsa_key, algorithms=["RS256"],
            audience="authenticated",
            issuer=f"{settings.SUPABASE_URL.removesuffix('/')}/auth/v1"
        )

        user_id: Optional[str] = payload.get("sub")
        user_email: Optional[str] = payload.get("email")

        if user_id is None or user_email is None:
            log.warning("User ID (sub) or email not found in JWT payload.")
            raise credentials_exception

        user_profile = db_supabase.get_user_profile_by_id(user_id)
        if user_profile is None:
            log.info(f"No local profile for valid JWT user {user_id}. Creating one.")
            user_profile = db_supabase.create_user_profile(user_id,
                                                           user_email)  # Ensure this returns the created profile or None
            if user_profile is None:
                log.error(f"Failed to create local profile for valid JWT user {user_id}.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="User profile creation failed after authentication.")

        log.info(f"User {user_profile.username} (ID: {user_profile.id}) authenticated successfully via JWT.")
        return UserPydantic(id=str(user_profile.id), email=user_profile.email, username=user_profile.username)

    except JWTError as e:
        log.warning(f"JWTError during token validation: {str(e)}", exc_info=True)
        raise credentials_exception
    except JOSEError as e:
        log.warning(f"JOSEError during token validation: {str(e)}", exc_info=True)
        raise credentials_exception
    except Exception as e:
        log.error(f"Unexpected error during token validation: {str(e)}", exc_info=True)
        raise credentials_exception
