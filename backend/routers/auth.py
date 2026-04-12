"""
Authentication router
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from models.database import get_db, User, Workspace, RefreshToken
from security.auth import (
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, verify_refresh_token,
    get_current_user, validate_password_strength,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: dict


# ── Helpers ───────────────────────────────────────────────────────

def _issue_tokens(user: User, db: Session) -> dict:
    """Issue an access + refresh token pair and persist the refresh token."""
    access = create_access_token({
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "username": user.username,
        "workspace_id": user.workspace_id,
    })
    refresh_raw = create_refresh_token(user.id)

    # Decode just to get jti + exp — no need to verify again
    import jose.jwt as _jwt, os
    payload = _jwt.decode(
        refresh_raw,
        os.getenv("SECRET_KEY", "autonomous-ai-analyst-secret-key-change-in-production"),
        algorithms=["HS256"],
    )
    rt = RefreshToken(
        jti=payload["jti"],
        user_id=user.id,
        expires_at=datetime.utcfromtimestamp(payload["exp"]),
    )
    db.add(rt)
    db.commit()

    return {
        "access_token": access,
        "refresh_token": refresh_raw,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "workspace_id": user.workspace_id,
            "is_superadmin": user.role == "superadmin",
        },
    }


def _user_response(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "is_superadmin": user.role == "superadmin",
    }


# ── CORS preflight ────────────────────────────────────────────────

@router.options("/register")
async def register_options():
    return {"ok": True}


@router.options("/login")
async def login_options():
    return {"ok": True}


# ── Register ──────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest, req: Request, db: Session = Depends(get_db)):
    # Password strength
    err = validate_password_strength(request.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Username length
    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")

    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    workspace = Workspace(id=str(uuid.uuid4()), name=f"{request.username}'s Workspace")
    db.add(workspace)
    db.flush()

    user = User(
        id=str(uuid.uuid4()),
        email=request.email,
        username=request.username,
        hashed_password=get_password_hash(request.password),
        role="analyst",
        workspace_id=workspace.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_tokens(user, db)


# ── Login ─────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, req: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is suspended. Contact your administrator.")

    # Check if the user's organization (workspace) is suspended
    if user.workspace_id:
        ws = db.query(Workspace).filter(Workspace.id == user.workspace_id).first()
        if ws and getattr(ws, "is_suspended", False):
            raise HTTPException(
                status_code=403,
                detail="Your organization account has been suspended. Contact support.",
            )

    return _issue_tokens(user, db)


# ── Refresh ───────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = verify_refresh_token(req.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    jti = payload.get("jti")
    stored = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not stored or stored.is_revoked:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    # Rotate: revoke old, issue new pair
    stored.is_revoked = True
    db.commit()

    return _issue_tokens(user, db)


# ── Logout ────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(req: RefreshRequest, db: Session = Depends(get_db)):
    """Revoke a refresh token (client should also discard the access token)."""
    payload = verify_refresh_token(req.refresh_token)
    if payload:
        jti = payload.get("jti")
        stored = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
        if stored:
            stored.is_revoked = True
            db.commit()
    return {"message": "Logged out"}


# ── Me ────────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "is_superadmin": user.role == "superadmin",
    }


@router.patch("/me")
async def update_me(
    req: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if req.username and req.username != user.username:
        if db.query(User).filter(User.username == req.username).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = req.username
    if req.email and req.email != user.email:
        if db.query(User).filter(User.email == req.email).first():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = req.email
    db.commit()
    return _user_response(user)


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    err = validate_password_strength(req.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    user.hashed_password = get_password_hash(req.new_password)
    # Revoke all existing refresh tokens on password change
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.is_revoked == False,
    ).update({"is_revoked": True})
    db.commit()
    return {"message": "Password updated. Please log in again."}


# ── Demo login ────────────────────────────────────────────────────

@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(db: Session = Depends(get_db)):
    """One-click demo access — creates a shared demo user on first call."""
    user = db.query(User).filter(User.email == "demo@analyst.ai").first()

    if not user:
        workspace = Workspace(id=str(uuid.uuid4()), name="Demo Workspace")
        db.add(workspace)
        db.flush()

        user = User(
            id=str(uuid.uuid4()),
            email="demo@analyst.ai",
            username="demo_analyst",
            hashed_password=get_password_hash("demo123"),
            role="admin",
            workspace_id=workspace.id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return _issue_tokens(user, db)
