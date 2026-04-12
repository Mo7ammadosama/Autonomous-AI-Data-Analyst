"""
SuperAdmin Router — /api/admin/

All endpoints require role='superadmin'. No workspace scoping — superadmin sees everything.
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.database import (
    get_db, User, Workspace, Dataset, Dashboard, AuditLog,
    LLMUsageLog, WorkspaceMember, RefreshToken,
)
from security.auth import require_superadmin

router = APIRouter(prefix="/api/admin", tags=["SuperAdmin"])


# ─── Schemas ──────────────────────────────────────────────────────

class SuspendRequest(BaseModel):
    reason: Optional[str] = None


class RoleChangeRequest(BaseModel):
    role: str  # viewer | analyst | admin  (cannot set superadmin via API)


# ─── Helper ───────────────────────────────────────────────────────

def _write_audit(
    db: Session,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[dict] = None,
):
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        user_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        created_at=datetime.utcnow(),
    ))


# ─── System Stats ─────────────────────────────────────────────────

@router.get("/stats")
def get_stats(
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    """System-wide statistics for the SuperAdmin overview dashboard."""
    total_users = db.query(func.count(User.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    suspended_users = total_users - active_users
    total_companies = db.query(func.count(Workspace.id)).scalar()

    suspended_companies = 0
    try:
        suspended_companies = db.query(func.count(Workspace.id)).filter(
            Workspace.is_suspended == True
        ).scalar()
    except Exception:
        pass

    total_datasets = db.query(func.count(Dataset.id)).scalar()
    total_dashboards = db.query(func.count(Dashboard.id)).scalar()

    # LLM usage today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    llm_today = db.query(
        func.count(LLMUsageLog.id),
        func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0),
    ).filter(LLMUsageLog.created_at >= today).first()

    # New users this week
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_users_week = db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "suspended_users": suspended_users,
        "total_companies": total_companies,
        "active_companies": total_companies - suspended_companies,
        "suspended_companies": suspended_companies,
        "total_datasets": total_datasets,
        "total_dashboards": total_dashboards,
        "llm_requests_today": llm_today[0] if llm_today else 0,
        "llm_cost_today_usd": round(float(llm_today[1]) if llm_today else 0.0, 4),
        "new_users_this_week": new_users_week,
    }


@router.get("/health")
def get_health(
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    """System health — DB status, version, environment."""
    import os, time
    t0 = time.time()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "healthy"
        db_latency_ms = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        db_status = f"error: {e}"
        db_latency_ms = -1

    return {
        "db_status": db_status,
        "db_latency_ms": db_latency_ms,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── Company (Workspace) Management ───────────────────────────────

@router.get("/companies")
def list_companies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),  # active | suspended
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    """List all companies/workspaces with stats."""
    q = db.query(Workspace)
    if search:
        q = q.filter(Workspace.name.ilike(f"%{search}%"))
    if status == "suspended":
        try:
            q = q.filter(Workspace.is_suspended == True)
        except Exception:
            pass
    elif status == "active":
        try:
            q = q.filter(Workspace.is_suspended == False)
        except Exception:
            pass

    total = q.count()
    workspaces = q.order_by(Workspace.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for ws in workspaces:
        member_count = db.query(func.count(WorkspaceMember.id)).filter(
            WorkspaceMember.workspace_id == ws.id
        ).scalar()
        dataset_count = db.query(func.count(Dataset.id)).filter(
            Dataset.workspace_id == ws.id
        ).scalar()
        result.append({
            "id": ws.id,
            "name": ws.name,
            "description": ws.description,
            "plan": ws.plan,
            "member_count": member_count,
            "dataset_count": dataset_count,
            "is_suspended": getattr(ws, "is_suspended", False),
            "suspended_reason": getattr(ws, "suspended_reason", None),
            "created_at": ws.created_at,
        })
    return {"total": total, "companies": result}


@router.get("/companies/{workspace_id}")
def get_company(
    workspace_id: str,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    """Get full company details + member list + stats."""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Company not found")

    members = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )

    dataset_count = db.query(func.count(Dataset.id)).filter(Dataset.workspace_id == workspace_id).scalar()

    return {
        "id": ws.id,
        "name": ws.name,
        "description": ws.description,
        "plan": ws.plan,
        "is_suspended": getattr(ws, "is_suspended", False),
        "suspended_reason": getattr(ws, "suspended_reason", None),
        "suspended_at": getattr(ws, "suspended_at", None),
        "created_at": ws.created_at,
        "dataset_count": dataset_count,
        "members": [
            {
                "user_id": m.user_id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "workspace_role": m.role,
                "joined_at": m.joined_at,
                "is_active": u.is_active,
            }
            for m, u in members
        ],
    }


@router.patch("/companies/{workspace_id}/suspend")
def suspend_company(
    workspace_id: str,
    body: SuspendRequest,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Company not found")

    ws.is_suspended = True
    ws.suspended_reason = body.reason
    ws.suspended_at = datetime.utcnow()
    _write_audit(db, current_user["sub"], "suspend_company", "workspace", workspace_id,
                 {"reason": body.reason})
    db.commit()
    return {"status": "suspended", "workspace_id": workspace_id}


@router.patch("/companies/{workspace_id}/activate")
def activate_company(
    workspace_id: str,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Company not found")

    ws.is_suspended = False
    ws.suspended_reason = None
    ws.suspended_at = None
    _write_audit(db, current_user["sub"], "activate_company", "workspace", workspace_id)
    db.commit()
    return {"status": "active", "workspace_id": workspace_id}


@router.delete("/companies/{workspace_id}")
def delete_company(
    workspace_id: str,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Company not found")

    # Unlink users from this workspace (don't delete users)
    db.query(User).filter(User.workspace_id == workspace_id).update({"workspace_id": None})
    db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).delete()

    _write_audit(db, current_user["sub"], "delete_company", "workspace", workspace_id,
                 {"name": ws.name})
    db.delete(ws)
    db.commit()
    return {"status": "deleted", "workspace_id": workspace_id}


# ─── User Management ──────────────────────────────────────────────

@router.get("/users")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),  # active | suspended
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    """List all users across all companies."""
    q = db.query(User)
    if search:
        q = q.filter(or_(
            User.username.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%"),
        ))
    if role:
        q = q.filter(User.role == role)
    if workspace_id:
        q = q.filter(User.workspace_id == workspace_id)
    if status == "suspended":
        q = q.filter(User.is_active == False)
    elif status == "active":
        q = q.filter(User.is_active == True)

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for u in users:
        dataset_count = db.query(func.count(Dataset.id)).filter(Dataset.owner_id == u.id).scalar()
        ws_name = None
        if u.workspace_id:
            ws = db.query(Workspace.name).filter(Workspace.id == u.workspace_id).first()
            ws_name = ws[0] if ws else None
        result.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "workspace_id": u.workspace_id,
            "workspace_name": ws_name,
            "dataset_count": dataset_count,
            "created_at": u.created_at,
        })
    return {"total": total, "users": result}


@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    dataset_count = db.query(func.count(Dataset.id)).filter(Dataset.owner_id == user_id).scalar()
    dashboard_count = db.query(func.count(Dashboard.id)).filter(Dashboard.user_id == user_id).scalar()
    ws = None
    if u.workspace_id:
        ws = db.query(Workspace).filter(Workspace.id == u.workspace_id).first()

    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "workspace_id": u.workspace_id,
        "workspace_name": ws.name if ws else None,
        "dataset_count": dataset_count,
        "dashboard_count": dashboard_count,
        "created_at": u.created_at,
    }


@router.patch("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    body: SuspendRequest,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    if user_id == current_user["sub"]:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.is_active = False
    # Revoke all refresh tokens
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked == False,
    ).update({"is_revoked": True})
    _write_audit(db, current_user["sub"], "suspend_user", "user", user_id,
                 {"reason": body.reason, "username": u.username})
    db.commit()
    return {"status": "suspended", "user_id": user_id}


@router.patch("/users/{user_id}/activate")
def activate_user(
    user_id: str,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.is_active = True
    _write_audit(db, current_user["sub"], "activate_user", "user", user_id,
                 {"username": u.username})
    db.commit()
    return {"status": "active", "user_id": user_id}


@router.patch("/users/{user_id}/role")
def change_user_role(
    user_id: str,
    body: RoleChangeRequest,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    allowed_roles = {"viewer", "analyst", "admin"}
    if body.role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(allowed_roles)}")

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == "superadmin":
        raise HTTPException(status_code=400, detail="Cannot change superadmin role")

    old_role = u.role
    u.role = body.role
    _write_audit(db, current_user["sub"], "change_user_role", "user", user_id,
                 {"from": old_role, "to": body.role, "username": u.username})
    db.commit()
    return {"status": "updated", "user_id": user_id, "new_role": body.role}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    if user_id == current_user["sub"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.role == "superadmin":
        raise HTTPException(status_code=400, detail="Cannot delete another superadmin")

    _write_audit(db, current_user["sub"], "delete_user", "user", user_id,
                 {"username": u.username, "email": u.email})
    db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete()
    db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user_id).delete()
    db.delete(u)
    db.commit()
    return {"status": "deleted", "user_id": user_id}


# ─── Audit Logs ───────────────────────────────────────────────────

@router.get("/audit-logs")
def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if from_date:
        q = q.filter(AuditLog.created_at >= datetime.fromisoformat(from_date))
    if to_date:
        q = q.filter(AuditLog.created_at <= datetime.fromisoformat(to_date))

    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

    # Enrich with usernames
    user_cache = {}
    result = []
    for log in logs:
        if log.user_id and log.user_id not in user_cache:
            u = db.query(User.username, User.email).filter(User.id == log.user_id).first()
            user_cache[log.user_id] = u[0] if u else "unknown"
        result.append({
            "id": log.id,
            "actor_id": log.user_id,
            "actor_username": user_cache.get(log.user_id, "system"),
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at,
        })
    return {"total": total, "logs": result}


# ─── LLM Usage & Cost ─────────────────────────────────────────────

@router.get("/llm-usage")
def get_llm_usage(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    group_by: Optional[str] = Query("day"),  # day | user | model
    current_user: dict = Depends(require_superadmin()),
    db: Session = Depends(get_db),
):
    q = db.query(LLMUsageLog)
    if from_date:
        q = q.filter(LLMUsageLog.created_at >= datetime.fromisoformat(from_date))
    if to_date:
        q = q.filter(LLMUsageLog.created_at <= datetime.fromisoformat(to_date))

    logs = q.all()

    # Aggregate
    from collections import defaultdict
    groups = defaultdict(lambda: {"requests": 0, "total_tokens": 0, "cost_usd": 0.0, "errors": 0})

    for log in logs:
        if group_by == "user":
            key = log.user_id or "anonymous"
        elif group_by == "model":
            key = log.model
        else:  # day
            key = log.created_at.strftime("%Y-%m-%d") if log.created_at else "unknown"

        groups[key]["requests"] += 1
        groups[key]["total_tokens"] += (log.prompt_tokens or 0) + (log.completion_tokens or 0)
        groups[key]["cost_usd"] += log.cost_usd or 0.0
        if not log.success:
            groups[key]["errors"] += 1

    # Sort
    sorted_groups = sorted(groups.items(), key=lambda x: x[1]["cost_usd"], reverse=True)

    total_cost = sum(v["cost_usd"] for v in groups.values())
    total_requests = sum(v["requests"] for v in groups.values())

    return {
        "total_requests": total_requests,
        "total_cost_usd": round(total_cost, 4),
        "group_by": group_by,
        "breakdown": [
            {"key": k, **{kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in v.items()}}
            for k, v in sorted_groups
        ],
    }
