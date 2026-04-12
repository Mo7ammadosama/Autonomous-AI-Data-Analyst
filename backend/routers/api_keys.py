"""
API Keys router — programmatic access key management.

Endpoints:
  GET    /api/auth/api-keys            list user's API keys
  POST   /api/auth/api-keys            create a new API key
  DELETE /api/auth/api-keys/{id}       revoke an API key
  PATCH  /api/auth/api-keys/{id}       update name/scopes
"""

import hashlib
import secrets
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, ApiKey
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

_KEY_PREFIX = "dm_"      # datamind prefix for easy identification
_KEY_BYTES = 32          # 256-bit entropy


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKeyCreate(BaseModel):
    name: str
    scopes: Optional[List[str]] = None
    expires_days: Optional[int] = None   # None = never expires


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    keys = db.query(ApiKey).filter(
        ApiKey.user_id == current_user["sub"]
    ).order_by(ApiKey.created_at.desc()).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes or [],
            "is_active": k.is_active,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "created_at": k.created_at.isoformat(),
        }
        for k in keys
    ]


@router.post("/", status_code=201)
async def create_api_key(
    req: ApiKeyCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new API key. The raw key is returned ONCE — store it securely.
    Only the hashed version is stored on the server.
    """
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Key name is required")

    # Check max keys per user
    existing_count = db.query(ApiKey).filter(
        ApiKey.user_id == current_user["sub"],
        ApiKey.is_active == True,
    ).count()
    if existing_count >= 20:
        raise HTTPException(status_code=400, detail="Maximum of 20 active API keys allowed")

    raw_key = _KEY_PREFIX + secrets.token_urlsafe(_KEY_BYTES)
    key_prefix = raw_key[:12]   # "dm_" + 9 chars shown in UI

    expires_at = None
    if req.expires_days:
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(days=req.expires_days)

    api_key = ApiKey(
        user_id=current_user["sub"],
        name=req.name.strip(),
        key_hash=_hash_key(raw_key),
        key_prefix=key_prefix,
        scopes=req.scopes or ["read", "write"],
        expires_at=expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,                   # ← only returned once
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        "created_at": api_key.created_at.isoformat(),
        "warning": "Store this key securely. It will not be shown again.",
    }


@router.patch("/{key_id}")
async def update_api_key(
    key_id: str,
    req: ApiKeyUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == current_user["sub"],
    ).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    if req.name is not None:
        key.name = req.name
    if req.is_active is not None:
        key.is_active = req.is_active
    db.commit()
    return {"message": "API key updated", "id": key.id}


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == current_user["sub"],
    ).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(key)
    db.commit()
