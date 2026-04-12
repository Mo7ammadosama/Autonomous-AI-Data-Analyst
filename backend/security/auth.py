"""
Security utilities: JWT, password hashing, auth
"""

import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "autonomous-ai-analyst-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15      # Short-lived access token
REFRESH_TOKEN_EXPIRE_DAYS = 7         # Long-lived refresh token

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


# ── Password utilities ────────────────────────────────────────────

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt 5.x enforces the 72-byte limit strictly — truncate to match hashing
    return pwd_context.verify(plain_password[:72], hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])


def validate_password_strength(password: str) -> Optional[str]:
    """
    Returns an error message string if weak, None if strong enough.
    Rules: ≥8 chars, at least one digit or special character.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[0-9!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return "Password must contain at least one number or special character"
    return None


# ── Token creation ────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """
    Creates a signed JWT refresh token (7-day expiry).
    The jti (JWT ID) allows per-token revocation in the DB.
    """
    jti = secrets.token_hex(16)
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "jti": jti, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Token verification ────────────────────────────────────────────

def verify_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_refresh_token(token: str) -> Optional[dict]:
    """Decodes and validates a refresh token. Returns payload or None."""
    payload = verify_token(token)
    if payload and payload.get("type") == "refresh":
        return payload
    return None


# ── FastAPI dependencies ──────────────────────────────────────────

def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Returns user payload or None if not authenticated."""
    if not credentials:
        return None
    payload = verify_token(credentials.credentials)
    if payload and payload.get("type") != "refresh":
        return payload
    return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Requires a valid access token."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if payload.get("type") == "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Use access token, not refresh token")
    return payload


ROLE_HIERARCHY = {"viewer": 0, "analyst": 1, "admin": 2, "superadmin": 3}


def require_role(required_role: str):
    def role_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role", "viewer")
        if ROLE_HIERARCHY.get(user_role, 0) < ROLE_HIERARCHY.get(required_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


def require_superadmin():
    """Strict check: only role='superadmin' passes. No numeric promotion."""
    def checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SuperAdmin access required",
            )
        return current_user
    return checker


def get_workspace_scope(current_user: dict) -> dict:
    """
    Returns scoping context for data-isolation queries.
      - SuperAdmin: is_superadmin=True → bypass all workspace filters
      - Normal user: filter by (user_id OR workspace_id)
    """
    return {
        "user_id": current_user.get("sub") or current_user.get("id"),
        "workspace_id": current_user.get("workspace_id"),
        "is_superadmin": current_user.get("role") == "superadmin",
    }
