"""
Personalized AI Digest Router — /api/digest/

Manage digest configuration and trigger on-demand sends.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, DigestConfig
from security.auth import get_current_user

router = APIRouter(prefix="/api/digest", tags=["Personalized Digest"])


# ─── Schemas ───────────────────────────────────────────────────

class DigestConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    frequency: Optional[str] = None              # daily | weekly
    send_hour: Optional[int] = None              # 0-23 UTC
    send_day: Optional[str] = None               # monday-sunday (for weekly)
    include_anomalies: Optional[bool] = None
    include_top_changes: Optional[bool] = None
    include_suggestions: Optional[bool] = None
    include_data_quality: Optional[bool] = None
    monitored_datasets: Optional[List[str]] = None
    monitored_metrics: Optional[List[str]] = None
    delivery_email: Optional[str] = None
    delivery_slack: Optional[bool] = None
    slack_webhook_url: Optional[str] = None


# ─── Helpers ───────────────────────────────────────────────────

def _ensure_config(user_id: str, db: Session) -> DigestConfig:
    config = db.query(DigestConfig).filter(DigestConfig.user_id == user_id).first()
    if not config:
        config = DigestConfig(user_id=user_id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


# ─── Endpoints ────────────────────────────────────────────────

@router.get("/config")
def get_digest_config(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's digest configuration."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    config = _ensure_config(uid, db)
    return _config_out(config)


@router.post("/configure")
def update_digest_config(
    body: DigestConfigUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update digest delivery preferences."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    config = _ensure_config(uid, db)
    updates = body.dict(exclude_none=True)

    if "frequency" in updates and updates["frequency"] not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="frequency must be daily | weekly")
    if "send_hour" in updates and not (0 <= updates["send_hour"] <= 23):
        raise HTTPException(status_code=400, detail="send_hour must be 0-23")

    for k, v in updates.items():
        setattr(config, k, v)
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return {"status": "updated", "config": _config_out(config)}


@router.get("/preview")
async def preview_digest(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview the digest content without sending it."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    config = _ensure_config(uid, db)
    from services.digest_generator import collect_digest_data, build_digest_html
    days = 1 if config.frequency == "daily" else 7
    data = await collect_digest_data(uid, days=days)
    html = build_digest_html(
        user_name=getattr(current_user, "username", "User"),
        frequency=config.frequency,
        anomalies=data["anomalies"],
        top_changes=data["top_changes"],
        suggestions=data["suggestions"],
        quality_issues=data["quality_issues"],
    )
    return {
        "data": data,
        "html_preview": html,
        "frequency": config.frequency,
    }


@router.post("/send-now")
async def send_digest_now(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger an immediate digest send for testing."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    config = _ensure_config(uid, db)
    if not config.is_enabled:
        raise HTTPException(status_code=400, detail="Digest is not enabled. Enable it first in /configure.")
    from services.digest_generator import send_digest_to_user
    result = await send_digest_to_user(uid, config)
    return {"status": "sent", "result": result}


def _config_out(c: DigestConfig) -> dict:
    return {
        "is_enabled": c.is_enabled,
        "frequency": c.frequency,
        "send_hour": c.send_hour,
        "send_day": c.send_day,
        "include_anomalies": c.include_anomalies,
        "include_top_changes": c.include_top_changes,
        "include_suggestions": c.include_suggestions,
        "include_data_quality": c.include_data_quality,
        "monitored_datasets": c.monitored_datasets,
        "monitored_metrics": c.monitored_metrics,
        "delivery_email": c.delivery_email,
        "delivery_slack": c.delivery_slack,
        "slack_webhook_url": c.slack_webhook_url,
        "last_sent_at": c.last_sent_at,
        "updated_at": c.updated_at,
    }
