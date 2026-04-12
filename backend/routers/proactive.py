"""
Proactive Intelligence Router — /api/proactive/

Endpoints for the user's personal Intelligence Feed (Tableau Pulse style).
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, ProactiveInsight, ProactiveConfig
from security.auth import get_current_user
from services.proactive_monitor import ensure_default_config

router = APIRouter(prefix="/api/proactive", tags=["Proactive Intelligence"])


# ─── Schemas ─────────────────────────────────────────────────

class ProactiveConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    scan_frequency_minutes: Optional[int] = None
    notify_websocket: Optional[bool] = None
    notify_email: Optional[bool] = None
    notify_slack: Optional[bool] = None
    slack_webhook_url: Optional[str] = None
    monitored_datasets: Optional[List[str]] = None
    anomaly_sensitivity: Optional[str] = None  # low | medium | high


class InsightOut(BaseModel):
    id: str
    dataset_id: Optional[str]
    metric_name: Optional[str]
    insight_type: str
    change_pct: Optional[float]
    current_value: Optional[float]
    previous_value: Optional[float]
    drivers: Optional[list]
    narrative: Optional[str]
    severity: str
    is_read: bool
    sent_via: Optional[list]
    created_at: datetime

    class Config:
        from_attributes = True


def _uid(current_user) -> str:
    """Extract user ID from either a dict (JWT payload) or an object with .id."""
    if isinstance(current_user, dict):
        return current_user["sub"]
    return current_user.id


# ─── Endpoints ───────────────────────────────────────────────

@router.get("/feed", response_model=List[InsightOut])
def get_intelligence_feed(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    severity: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Personal intelligence feed — proactively generated insights for this user."""
    uid = _uid(current_user)
    q = (
        db.query(ProactiveInsight)
        .filter(ProactiveInsight.user_id == uid)
    )
    if unread_only:
        q = q.filter(ProactiveInsight.is_read == False)
    if severity:
        q = q.filter(ProactiveInsight.severity == severity)
    insights = (
        q.order_by(ProactiveInsight.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return insights


@router.get("/feed/unread-count")
def get_unread_count(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get count of unread proactive insights (for sidebar badge)."""
    uid = _uid(current_user)
    count = (
        db.query(ProactiveInsight)
        .filter(
            ProactiveInsight.user_id == uid,
            ProactiveInsight.is_read == False,
        )
        .count()
    )
    return {"unread_count": count}


@router.post("/feed/{insight_id}/read")
def mark_as_read(
    insight_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a single insight as read."""
    uid = _uid(current_user)
    insight = (
        db.query(ProactiveInsight)
        .filter(
            ProactiveInsight.id == insight_id,
            ProactiveInsight.user_id == uid,
        )
        .first()
    )
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.is_read = True
    db.commit()
    return {"status": "ok"}


@router.post("/feed/mark-all-read")
def mark_all_read(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark all insights as read."""
    uid = _uid(current_user)
    db.query(ProactiveInsight).filter(
        ProactiveInsight.user_id == uid,
        ProactiveInsight.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"status": "ok"}


@router.get("/config")
def get_config(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's proactive monitoring configuration."""
    uid = _uid(current_user)
    config = ensure_default_config(uid, db)
    return {
        "is_enabled": config.is_enabled,
        "scan_frequency_minutes": config.scan_frequency_minutes,
        "notify_websocket": config.notify_websocket,
        "notify_email": config.notify_email,
        "notify_slack": config.notify_slack,
        "slack_webhook_url": config.slack_webhook_url,
        "monitored_datasets": config.monitored_datasets,
        "anomaly_sensitivity": config.anomaly_sensitivity,
        "updated_at": config.updated_at,
    }


@router.post("/configure")
def update_config(
    body: ProactiveConfigUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update proactive monitoring configuration."""
    uid = _uid(current_user)
    config = ensure_default_config(uid, db)
    updates = body.dict(exclude_none=True)
    if "scan_frequency_minutes" in updates:
        freq = updates["scan_frequency_minutes"]
        if freq < 15:
            raise HTTPException(status_code=400, detail="Minimum scan frequency is 15 minutes")
    if "anomaly_sensitivity" in updates:
        if updates["anomaly_sensitivity"] not in ("low", "medium", "high"):
            raise HTTPException(status_code=400, detail="sensitivity must be low | medium | high")
    for k, v in updates.items():
        setattr(config, k, v)
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return {"status": "updated", "config": updates}


@router.post("/scan-now")
async def trigger_scan_now(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger a proactive scan for the current user (runs immediately)."""
    uid = _uid(current_user)
    from services.proactive_monitor import run_proactive_scan
    stats = await run_proactive_scan(user_id=uid)
    return {"status": "scan_complete", "stats": stats}


@router.get("/history")
def get_history(
    days: int = Query(7, ge=1, le=90),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get history of all proactive insights sent in the last N days."""
    from datetime import timedelta
    uid = _uid(current_user)
    cutoff = datetime.utcnow() - timedelta(days=days)
    insights = (
        db.query(ProactiveInsight)
        .filter(
            ProactiveInsight.user_id == uid,
            ProactiveInsight.created_at >= cutoff,
        )
        .order_by(ProactiveInsight.created_at.desc())
        .all()
    )
    by_type = {}
    for ins in insights:
        by_type.setdefault(ins.insight_type, []).append(ins.id)
    return {
        "total": len(insights),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "insights": [
            {
                "id": i.id,
                "metric_name": i.metric_name,
                "insight_type": i.insight_type,
                "severity": i.severity,
                "narrative": i.narrative,
                "created_at": i.created_at,
            }
            for i in insights
        ],
    }
