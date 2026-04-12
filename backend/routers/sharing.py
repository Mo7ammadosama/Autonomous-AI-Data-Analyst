"""
Public Dashboard Sharing router.

Endpoints:
  POST /api/dashboards/{id}/share         create a public share link
  GET  /api/shared/{token}               view shared dashboard (no auth)
  DELETE /api/dashboards/{id}/share      revoke all share links
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Dashboard, SharedDashboard
from security.auth import get_current_user

router = APIRouter()          # mounted at /api/dashboards
public_router = APIRouter()  # mounted at /api/shared
logger = logging.getLogger(__name__)


class ShareRequest(BaseModel):
    expires_days: Optional[int] = None   # None = never expires


@router.post("/{dashboard_id}/share", status_code=201)
async def create_share_link(
    dashboard_id: str,
    req: ShareRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a public share token for a dashboard."""
    dash = db.query(Dashboard).filter(
        Dashboard.id == dashboard_id,
        Dashboard.user_id == current_user["sub"],
    ).first()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    token = uuid.uuid4().hex
    expires_at = None
    if req.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=req.expires_days)

    shared = SharedDashboard(
        id=str(uuid.uuid4()),
        dashboard_id=dashboard_id,
        token=token,
        created_by=current_user["sub"],
        expires_at=expires_at,
    )
    db.add(shared)
    db.commit()
    db.refresh(shared)
    return {
        "token": token,
        "share_url": f"/share/{token}",
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@public_router.get("/{token}")
async def get_shared_dashboard(
    token: str,
    db: Session = Depends(get_db),
):
    """Return a shared dashboard by token — no authentication required."""
    shared = db.query(SharedDashboard).filter(
        SharedDashboard.token == token,
        SharedDashboard.is_active == True,
    ).first()
    if not shared:
        raise HTTPException(status_code=404, detail="Share link not found or revoked")
    if shared.expires_at and shared.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Share link has expired")

    dash = db.query(Dashboard).filter(Dashboard.id == shared.dashboard_id).first()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Increment view count
    shared.view_count = (shared.view_count or 0) + 1
    db.commit()

    return {
        "id": dash.id,
        "name": getattr(dash, "title", getattr(dash, "name", "Untitled")),
        "description": getattr(dash, "description", None),
        "charts": dash.charts or [],
        "layout": dash.layout or {},
        "view_count": shared.view_count,
        "created_at": dash.created_at.isoformat(),
    }


@router.delete("/{dashboard_id}/share", status_code=204)
async def revoke_share_links(
    dashboard_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke all active share links for a dashboard."""
    dash = db.query(Dashboard).filter(
        Dashboard.id == dashboard_id,
        Dashboard.user_id == current_user["sub"],
    ).first()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    db.query(SharedDashboard).filter(
        SharedDashboard.dashboard_id == dashboard_id,
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()


@router.get("/{dashboard_id}/shares")
async def list_share_links(
    dashboard_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all share links for a dashboard."""
    dash = db.query(Dashboard).filter(
        Dashboard.id == dashboard_id,
        Dashboard.user_id == current_user["sub"],
    ).first()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    shares = db.query(SharedDashboard).filter(
        SharedDashboard.dashboard_id == dashboard_id,
        SharedDashboard.is_active == True,
    ).all()
    return [
        {
            "token": s.token,
            "share_url": f"/share/{s.token}",
            "view_count": s.view_count,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in shares
    ]
