"""
Alerts Router — CRUD + evaluation for user-defined data alerts.

Endpoints:
  POST   /api/alerts/                         Create alert
  GET    /api/alerts/                         List user alerts
  GET    /api/alerts/{id}                     Get alert details + logs
  PUT    /api/alerts/{id}                     Update alert
  DELETE /api/alerts/{id}                     Delete alert
  POST   /api/alerts/{id}/evaluate            Manually evaluate alert against live data
  POST   /api/alerts/evaluate-all/{dataset_id} Evaluate all alerts for a dataset
  GET    /api/alerts/{id}/logs                Alert trigger history
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging

from models.database import get_db, Alert, AlertLog, Dataset
from security.auth import get_current_user
from services.data_processor import load_dataset
from services.alert_service import AlertService

logger = logging.getLogger(__name__)
router = APIRouter()
_alert_svc = AlertService()


# ── Pydantic schemas ─────────────────────────────────────────────

class AlertCreate(BaseModel):
    name: str
    description: Optional[str] = None
    dataset_id: Optional[str] = None
    column_name: Optional[str] = None
    condition: str                      # gt | lt | gte | lte | eq | anomaly
    threshold: Optional[float] = None
    aggregation: Optional[str] = "mean"
    # Email
    notify_email: bool = True
    email_recipient: Optional[str] = None
    # Slack
    notify_slack: bool = False
    slack_webhook_url: Optional[str] = None
    # Teams
    notify_teams: bool = False
    teams_webhook_url: Optional[str] = None
    # Telegram
    notify_telegram: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    column_name: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    aggregation: Optional[str] = None
    notify_email: Optional[bool] = None
    email_recipient: Optional[str] = None
    is_active: Optional[bool] = None
    # Slack
    notify_slack: Optional[bool] = None
    slack_webhook_url: Optional[str] = None
    # Teams
    notify_teams: Optional[bool] = None
    teams_webhook_url: Optional[str] = None
    # Telegram
    notify_telegram: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


def _alert_to_dict(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "name": alert.name,
        "description": alert.description,
        "dataset_id": alert.dataset_id,
        "column_name": alert.column_name,
        "condition": alert.condition,
        "threshold": alert.threshold,
        "aggregation": alert.aggregation,
        "notify_email": alert.notify_email,
        "email_recipient": alert.email_recipient,
        "notify_slack": getattr(alert, "notify_slack", False),
        "slack_webhook_url": getattr(alert, "slack_webhook_url", None),
        "notify_teams": getattr(alert, "notify_teams", False),
        "teams_webhook_url": getattr(alert, "teams_webhook_url", None),
        "notify_telegram": getattr(alert, "notify_telegram", False),
        "telegram_chat_id": getattr(alert, "telegram_chat_id", None),
        "is_active": alert.is_active,
        "status": alert.status,
        "last_checked": alert.last_checked.isoformat() if alert.last_checked else None,
        "last_triggered": alert.last_triggered.isoformat() if alert.last_triggered else None,
        "trigger_count": alert.trigger_count,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new data alert."""
    valid_conditions = {"gt", "lt", "gte", "lte", "eq", "anomaly"}
    if payload.condition not in valid_conditions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition '{payload.condition}'. Must be one of: {valid_conditions}",
        )
    if payload.condition != "anomaly" and payload.threshold is None:
        raise HTTPException(status_code=400, detail="Threshold is required for non-anomaly conditions.")

    alert = Alert(
        user_id=current_user["sub"],
        dataset_id=payload.dataset_id,
        name=payload.name,
        description=payload.description,
        column_name=payload.column_name,
        condition=payload.condition,
        threshold=payload.threshold,
        aggregation=payload.aggregation or "mean",
        notify_email=payload.notify_email,
        email_recipient=payload.email_recipient,
        notify_slack=payload.notify_slack,
        slack_webhook_url=payload.slack_webhook_url,
        notify_teams=payload.notify_teams,
        teams_webhook_url=payload.teams_webhook_url,
        notify_telegram=payload.notify_telegram,
        telegram_bot_token=payload.telegram_bot_token,
        telegram_chat_id=payload.telegram_chat_id,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.get("/")
async def list_alerts(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all alerts for the current user."""
    alerts = db.query(Alert).filter(Alert.user_id == current_user["sub"]).order_by(Alert.created_at.desc()).all()
    return [_alert_to_dict(a) for a in alerts]


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == current_user["sub"]).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _alert_to_dict(alert)


@router.put("/{alert_id}")
async def update_alert(
    alert_id: str,
    payload: AlertUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == current_user["sub"]).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    for field, value in payload.dict(exclude_none=True).items():
        setattr(alert, field, value)
    alert.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return _alert_to_dict(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == current_user["sub"]).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()


@router.get("/{alert_id}/logs")
async def alert_logs(
    alert_id: str,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve trigger history for an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == current_user["sub"]).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    logs = (
        db.query(AlertLog)
        .filter(AlertLog.alert_id == alert_id)
        .order_by(AlertLog.triggered_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "triggered_at": log.triggered_at.isoformat(),
            "actual_value": log.actual_value,
            "message": log.message,
            "notified": log.notified,
        }
        for log in logs
    ]


@router.post("/{alert_id}/evaluate")
async def evaluate_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually evaluate a single alert against its linked dataset."""
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == current_user["sub"]).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if not alert.dataset_id:
        raise HTTPException(status_code=400, detail="Alert has no linked dataset.")

    dataset = db.query(Dataset).filter(Dataset.id == alert.dataset_id).first()
    if not dataset or dataset.status != "ready":
        raise HTTPException(status_code=400, detail="Dataset not ready.")

    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {e}")

    results = _alert_svc.evaluate_all([alert], df, dataset.name, db)
    return {"results": results, "evaluated_at": datetime.utcnow().isoformat()}


@router.post("/evaluate-all/{dataset_id}")
async def evaluate_all_alerts(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate all active alerts linked to a specific dataset."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    if dataset.status != "ready":
        raise HTTPException(status_code=400, detail="Dataset not ready for evaluation.")

    alerts = db.query(Alert).filter(
        Alert.user_id == current_user["sub"],
        Alert.dataset_id == dataset_id,
        Alert.is_active == True,
    ).all()

    if not alerts:
        return {"message": "No active alerts for this dataset.", "results": []}

    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {e}")

    results = _alert_svc.evaluate_all(alerts, df, dataset.name, db)
    triggered = sum(1 for r in results if r["triggered"])
    return {
        "total_evaluated": len(results),
        "triggered": triggered,
        "results": results,
        "evaluated_at": datetime.utcnow().isoformat(),
    }
