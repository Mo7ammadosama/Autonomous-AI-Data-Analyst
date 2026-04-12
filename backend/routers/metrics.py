"""
Platform Metrics router — observability + Governed Semantic Metric Catalog.

GET  /api/metrics             — user usage stats
GET  /api/metrics/system      — platform-wide system health
POST /api/metrics/define      — create a metric definition
GET  /api/metrics/definitions — list governed metric definitions
GET  /api/metrics/search      — search metric definitions
GET  /api/metrics/definitions/{id}          — get single metric
PUT  /api/metrics/definitions/{id}          — update metric
DELETE /api/metrics/definitions/{id}        — soft-delete metric
POST /api/metrics/definitions/{id}/certify  — admin certify metric
GET  /api/metrics/definitions/{id}/lineage  — data lineage graph
GET  /api/metrics/suggest/{dataset_id}      — AI-suggest metrics from dataset
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.database import (
    get_db, User, Dataset, Dashboard, Alert, AlertLog,
    ChatSession, ChatMessage, NL2SQLQuery, Insight,
    ScheduledReport, DataConnection, AuditLog, MetricDefinition,
)
from security.auth import get_current_user
from services.cache_service import cache

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Schemas ────────────────────────────────────────────────────────

class MetricCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    sql_expression: Optional[str] = None
    dataset_id: Optional[str] = None
    source_columns: Optional[List[str]] = []
    approved_dimensions: Optional[List[str]] = []
    unit: Optional[str] = None
    direction: Optional[str] = "higher_is_better"
    tags: Optional[List[str]] = []


class MetricUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    sql_expression: Optional[str] = None
    source_columns: Optional[List[str]] = None
    approved_dimensions: Optional[List[str]] = None
    unit: Optional[str] = None
    direction: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ─── Semantic Metric Catalog Endpoints ─────────────────────────────

@router.post("/define")
def define_metric(
    body: MetricCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new governed metric definition."""
    from services.semantic_layer import create_metric
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    workspace_id = getattr(current_user, "workspace_id", None)
    metric = create_metric(
        db=db,
        owner_id=uid,
        workspace_id=workspace_id,
        **body.dict(exclude_none=True),
    )
    return _metric_out(metric)


@router.get("/definitions")
def list_metric_definitions(
    category: Optional[str] = Query(None),
    certified_only: bool = Query(False),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all governed metric definitions in the workspace."""
    from services.semantic_layer import list_metrics
    workspace_id = getattr(current_user, "workspace_id", None)
    metrics = list_metrics(db, workspace_id=workspace_id, category=category, certified_only=certified_only)
    return [_metric_out(m) for m in metrics]


@router.get("/search")
def search_metric_definitions(
    q: str = Query(..., min_length=1),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Full-text search across metric names, descriptions, and tags."""
    from services.semantic_layer import search_metrics
    workspace_id = getattr(current_user, "workspace_id", None)
    metrics = search_metrics(db, query=q, workspace_id=workspace_id)
    return [_metric_out(m) for m in metrics]


@router.get("/definitions/{metric_id}")
def get_metric_definition(
    metric_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single metric definition by ID."""
    from services.semantic_layer import get_metric
    metric = get_metric(db, metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    return _metric_out(metric)


@router.put("/definitions/{metric_id}")
def update_metric_definition(
    metric_id: str,
    body: MetricUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a metric definition (revokes certification if SQL changes)."""
    from services.semantic_layer import update_metric, get_metric
    metric = get_metric(db, metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    if metric.owner_id != uid:
        raise HTTPException(status_code=403, detail="Not the metric owner")
    updated = update_metric(db, metric_id, body.dict(exclude_none=True))
    return _metric_out(updated)


@router.delete("/definitions/{metric_id}")
def delete_metric_definition(
    metric_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a metric definition."""
    from services.semantic_layer import delete_metric, get_metric
    metric = get_metric(db, metric_id)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    if metric.owner_id != uid:
        raise HTTPException(status_code=403, detail="Not the metric owner")
    delete_metric(db, metric_id)
    return {"status": "deleted"}


@router.post("/definitions/{metric_id}/certify")
def certify_metric_definition(
    metric_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin: certify a metric definition as the authoritative source."""
    from services.semantic_layer import certify_metric
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    try:
        metric = certify_metric(db, metric_id, certified_by=uid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _metric_out(metric)


@router.get("/definitions/{metric_id}/lineage")
def get_metric_lineage(
    metric_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the data lineage graph for a metric."""
    from services.semantic_layer import get_lineage
    lineage = get_lineage(db, metric_id)
    if not lineage:
        raise HTTPException(status_code=404, detail="Metric not found")
    return lineage


@router.get("/suggest/{dataset_id}")
def suggest_metrics(
    dataset_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-suggest metric definitions based on dataset column names."""
    from services.semantic_layer import suggest_metrics_from_dataset
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    suggestions = suggest_metrics_from_dataset(db, dataset_id=dataset_id, owner_id=uid)
    return {"suggestions": suggestions, "count": len(suggestions)}


def _metric_out(m: MetricDefinition) -> Dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "display_name": m.display_name,
        "description": m.description,
        "category": m.category,
        "sql_expression": m.sql_expression,
        "dataset_id": m.dataset_id,
        "source_columns": m.source_columns,
        "approved_dimensions": m.approved_dimensions,
        "unit": m.unit,
        "direction": m.direction,
        "is_certified": m.is_certified,
        "certified_by": m.certified_by,
        "certified_at": m.certified_at,
        "tags": m.tags,
        "is_active": m.is_active,
        "owner_id": m.owner_id,
        "workspace_id": m.workspace_id,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }

CACHE_TTL = 60  # metrics cached for 60 seconds


@router.get("/")
async def user_metrics(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return usage statistics for the current user."""
    uid = current_user["sub"]
    cache_key = f"metrics:user:{uid}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Dataset stats
    ds_total = db.query(func.count(Dataset.id)).filter(Dataset.owner_id == uid).scalar() or 0
    ds_ready = db.query(func.count(Dataset.id)).filter(Dataset.owner_id == uid, Dataset.status == "ready").scalar() or 0
    ds_this_week = db.query(func.count(Dataset.id)).filter(Dataset.owner_id == uid, Dataset.created_at >= week_ago).scalar() or 0
    total_rows = db.query(func.sum(Dataset.row_count)).filter(Dataset.owner_id == uid).scalar() or 0
    total_size = db.query(func.sum(Dataset.file_size)).filter(Dataset.owner_id == uid).scalar() or 0

    # Chat stats
    sessions_total = db.query(func.count(ChatSession.id)).filter(ChatSession.user_id == uid).scalar() or 0
    messages_total = db.query(func.count(ChatMessage.id)).join(
        ChatSession, ChatMessage.session_id == ChatSession.id
    ).filter(ChatSession.user_id == uid).scalar() or 0

    # NL2SQL stats
    nl2sql_total = db.query(func.count(NL2SQLQuery.id)).filter(NL2SQLQuery.user_id == uid).scalar() or 0
    nl2sql_success = db.query(func.count(NL2SQLQuery.id)).filter(NL2SQLQuery.user_id == uid, NL2SQLQuery.success == True).scalar() or 0

    # Alerts
    alerts_total = db.query(func.count(Alert.id)).filter(Alert.user_id == uid).scalar() or 0
    alerts_active = db.query(func.count(Alert.id)).filter(Alert.user_id == uid, Alert.is_active == True).scalar() or 0
    alert_fires = db.query(func.count(AlertLog.id)).join(
        Alert, AlertLog.alert_id == Alert.id
    ).filter(Alert.user_id == uid).scalar() or 0
    alert_fires_week = db.query(func.count(AlertLog.id)).join(
        Alert, AlertLog.alert_id == Alert.id
    ).filter(Alert.user_id == uid, AlertLog.triggered_at >= week_ago).scalar() or 0

    # Dashboards
    dash_total = db.query(func.count(Dashboard.id)).filter(Dashboard.user_id == uid).scalar() or 0

    # Connections
    conn_total = db.query(func.count(DataConnection.id)).filter(DataConnection.user_id == uid).scalar() or 0

    # Scheduled reports
    sr_total = db.query(func.count(ScheduledReport.id)).filter(ScheduledReport.user_id == uid).scalar() or 0
    sr_active = db.query(func.count(ScheduledReport.id)).filter(ScheduledReport.user_id == uid, ScheduledReport.is_active == True).scalar() or 0

    result = {
        "generated_at": now.isoformat(),
        "datasets": {
            "total": ds_total,
            "ready": ds_ready,
            "uploaded_this_week": ds_this_week,
            "total_rows": int(total_rows),
            "total_size_bytes": int(total_size),
        },
        "ai": {
            "chat_sessions": sessions_total,
            "chat_messages": messages_total,
            "nl2sql_queries": nl2sql_total,
            "nl2sql_success_rate": round(nl2sql_success / max(nl2sql_total, 1) * 100, 1),
        },
        "alerts": {
            "total": alerts_total,
            "active": alerts_active,
            "total_triggers": alert_fires,
            "triggers_this_week": alert_fires_week,
        },
        "platform": {
            "dashboards": dash_total,
            "connections": conn_total,
            "scheduled_reports": sr_total,
        },
    }
    cache.set(cache_key, result, CACHE_TTL)
    return result


@router.get("/system")
async def system_metrics(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Platform-wide metrics — available to all users (aggregate/non-PII)."""
    cache_key = "metrics:system"
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users_day = db.query(func.count(AuditLog.user_id.distinct())).filter(
        AuditLog.created_at >= day_ago
    ).scalar() or 0
    active_users_week = db.query(func.count(AuditLog.user_id.distinct())).filter(
        AuditLog.created_at >= week_ago
    ).scalar() or 0
    total_datasets = db.query(func.count(Dataset.id)).scalar() or 0
    total_queries = db.query(func.count(NL2SQLQuery.id)).scalar() or 0
    total_dashboards = db.query(func.count(Dashboard.id)).scalar() or 0
    total_alerts = db.query(func.count(Alert.id)).scalar() or 0

    result = {
        "generated_at": now.isoformat(),
        "users": {
            "total": total_users,
            "active_last_24h": active_users_day,
            "active_last_7d": active_users_week,
        },
        "content": {
            "datasets": total_datasets,
            "dashboards": total_dashboards,
            "nl2sql_queries": total_queries,
            "alerts": total_alerts,
        },
        "platform_version": "2.0.0",
    }
    cache.set(cache_key, result, CACHE_TTL)
    return result
