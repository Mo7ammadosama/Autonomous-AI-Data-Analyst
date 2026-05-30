"""
Dashboards router

Endpoints:
  POST   /api/dashboards/                           Create dashboard
  POST   /api/dashboards/build-with-ai              AI dashboard builder
  GET    /api/dashboards/                           List dashboards
  GET    /api/dashboards/{id}                       Get dashboard
  PUT    /api/dashboards/{id}                       Update dashboard (auto-snapshots version)
  DELETE /api/dashboards/{id}                       Delete dashboard
  POST   /api/dashboards/{id}/duplicate             Duplicate dashboard
  PATCH  /api/dashboards/{id}/visibility            Toggle public/private

  Comments:
  GET    /api/dashboards/{id}/comments              List comments
  POST   /api/dashboards/{id}/comments              Create comment
  PUT    /api/dashboards/{id}/comments/{cid}        Update comment
  DELETE /api/dashboards/{id}/comments/{cid}        Delete comment
  POST   /api/dashboards/{id}/comments/{cid}/resolve Toggle resolved

  Versions:
  GET    /api/dashboards/{id}/versions              List version snapshots
  GET    /api/dashboards/{id}/versions/{n}          Get specific version
  POST   /api/dashboards/{id}/versions/{n}/restore  Restore snapshot
"""

from fastapi import APIRouter, HTTPException, Depends, status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import uuid
import logging
from datetime import datetime

from models.database import (
    get_db, Dashboard, Dataset,
    DashboardComment, DashboardVersion,
)
from services.data_processor import load_dataset
from services.ai_agent import AIDataAnalystAgent
from services.visualization import generate_auto_charts
from security.auth import get_current_user, get_workspace_scope
from sqlalchemy import or_

router = APIRouter()
logger = logging.getLogger(__name__)
agent = AIDataAnalystAgent()

MAX_VERSIONS = 50  # Maximum snapshots retained per dashboard


# ── Helpers ───────────────────────────────────────────────────────

def _dashboard_dict(d: Dashboard) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "description": d.description,
        "charts": d.charts,
        "chart_count": len(d.charts) if d.charts else 0,
        "layout": d.layout,
        "dataset_id": d.dataset_id,
        "is_public": d.is_public,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if getattr(d, "updated_at", None) else None,
    }


def _snapshot(dashboard: Dashboard, created_by: str, change_summary: str, db: Session):
    """Create a version snapshot. Prune to MAX_VERSIONS if exceeded."""
    existing = (
        db.query(DashboardVersion)
        .filter(DashboardVersion.dashboard_id == dashboard.id)
        .order_by(DashboardVersion.version_number.desc())
        .all()
    )
    next_version = (existing[0].version_number + 1) if existing else 1

    snap = DashboardVersion(
        dashboard_id=dashboard.id,
        version_number=next_version,
        title=dashboard.title,
        layout=dashboard.layout,
        charts=dashboard.charts,
        created_by=created_by,
        change_summary=change_summary,
    )
    db.add(snap)

    # Prune oldest versions if over limit
    if len(existing) >= MAX_VERSIONS:
        oldest = existing[MAX_VERSIONS - 1 :]
        for old in oldest:
            db.delete(old)


def _get_dashboard_or_404(dashboard_id: str, user_id: str, db: Session,
                           workspace_id: str = None, is_superadmin: bool = False) -> Dashboard:
    if is_superadmin:
        d = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    elif workspace_id:
        d = db.query(Dashboard).filter(
            Dashboard.id == dashboard_id,
            or_(Dashboard.user_id == user_id, Dashboard.workspace_id == workspace_id),
        ).first()
    else:
        d = db.query(Dashboard).filter(
            Dashboard.id == dashboard_id,
            Dashboard.user_id == user_id,
        ).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return d


def _get_comment_or_404(comment_id: str, dashboard_id: str, db: Session) -> DashboardComment:
    c = db.query(DashboardComment).filter(
        DashboardComment.id == comment_id,
        DashboardComment.dashboard_id == dashboard_id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    return c


# ── Pydantic schemas ──────────────────────────────────────────────

class DashboardCreate(BaseModel):
    title: str
    description: Optional[str] = None
    dataset_id: Optional[str] = None
    command: Optional[str] = None
    charts: Optional[List] = None


class DashboardUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    layout: Optional[Dict] = None
    charts: Optional[List] = None
    change_summary: Optional[str] = None


class AIBuildRequest(BaseModel):
    dataset_id: str
    prompt: str
    max_charts: Optional[int] = 6


class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[str] = None
    chart_index: Optional[int] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class CommentUpdate(BaseModel):
    content: str


# ── Dashboard CRUD ────────────────────────────────────────────────

@router.post("/", status_code=http_status.HTTP_201_CREATED)
async def create_dashboard(
    req: DashboardCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    charts = req.charts or []
    layout: Dict = {}

    if not charts and req.dataset_id:
        dataset = db.query(Dataset).filter(
            Dataset.id == req.dataset_id,
            Dataset.owner_id == current_user["sub"],
        ).first()
        if dataset:
            try:
                df = load_dataset(dataset.file_path, dataset.file_type)
                if req.command:
                    layout_data = agent.generate_dashboard(req.command, df)
                    charts = layout_data.get("charts", [])
                    layout = {
                        "title": layout_data.get("title", req.title),
                        "summary_stats": layout_data.get("summary_stats", {}),
                    }
                else:
                    charts = generate_auto_charts(df, max_charts=6)
            except Exception as e:
                logger.error(f"Dashboard generation error: {e}")

    dashboard = Dashboard(
        id=str(uuid.uuid4()),
        title=req.title,
        description=req.description,
        layout=layout,
        charts=charts,
        dataset_id=req.dataset_id,
        user_id=current_user["sub"],
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)
    return _dashboard_dict(dashboard)


@router.post("/build-with-ai")
async def build_dashboard_with_ai(
    req: AIBuildRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI-powered dashboard generation from a natural language prompt."""
    dataset = db.query(Dataset).filter(
        Dataset.id == req.dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        layout_data = agent.generate_dashboard(req.prompt, df)
        charts = layout_data.get("charts", [])
        if len(charts) > (req.max_charts or 6):
            charts = charts[: req.max_charts or 6]
        title = layout_data.get("title") or f"AI Dashboard: {dataset.name}"
        description = layout_data.get("description") or req.prompt
        dashboard = Dashboard(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            layout={
                "summary_stats": layout_data.get("summary_stats", {}),
                "ai_generated": True,
                "prompt": req.prompt,
            },
            charts=charts,
            dataset_id=req.dataset_id,
            user_id=current_user["sub"],
        )
        db.add(dashboard)
        db.commit()
        db.refresh(dashboard)
        result = _dashboard_dict(dashboard)
        result["chart_count"] = len(charts)
        return result
    except Exception as e:
        logger.error(f"AI Dashboard build error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_dashboards(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    scope = get_workspace_scope(current_user)
    if scope["is_superadmin"]:
        q = db.query(Dashboard)
    elif scope["workspace_id"]:
        q = db.query(Dashboard).filter(or_(
            Dashboard.user_id == scope["user_id"],
            Dashboard.workspace_id == scope["workspace_id"],
        ))
    else:
        q = db.query(Dashboard).filter(Dashboard.user_id == scope["user_id"])
    dashboards = q.order_by(Dashboard.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "description": d.description,
            "dataset_id": d.dataset_id,
            "chart_count": len(d.charts) if d.charts else 0,
            "is_public": d.is_public,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in dashboards
    ]


@router.get("/{dashboard_id}")
async def get_dashboard(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dashboard = _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    return _dashboard_dict(dashboard)


@router.put("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: str,
    req: DashboardUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dashboard = _get_dashboard_or_404(dashboard_id, current_user["sub"], db)

    # Auto-snapshot before applying changes
    _snapshot(
        dashboard,
        created_by=current_user["sub"],
        change_summary=req.change_summary or "Manual update",
        db=db,
    )

    if req.title is not None:
        dashboard.title = req.title
    if req.description is not None:
        dashboard.description = req.description
    if req.layout is not None:
        dashboard.layout = req.layout
    if req.charts is not None:
        dashboard.charts = req.charts

    if hasattr(dashboard, "updated_at"):
        dashboard.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dashboard)
    return _dashboard_dict(dashboard)


@router.delete("/{dashboard_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dashboard = _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    db.delete(dashboard)
    db.commit()


@router.post("/{dashboard_id}/duplicate")
async def duplicate_dashboard(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a copy of an existing dashboard."""
    original = _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    copy = Dashboard(
        id=str(uuid.uuid4()),
        title=f"{original.title} (Copy)",
        description=original.description,
        layout=original.layout,
        charts=original.charts,
        dataset_id=original.dataset_id,
        user_id=current_user["sub"],
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return {"id": copy.id, "title": copy.title, "created_at": copy.created_at.isoformat()}


@router.patch("/{dashboard_id}/visibility")
async def toggle_visibility(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Toggle public/private sharing for a dashboard."""
    dashboard = _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    dashboard.is_public = not dashboard.is_public
    db.commit()
    return {"id": dashboard.id, "is_public": dashboard.is_public}


# ── Comments ──────────────────────────────────────────────────────

@router.get("/{dashboard_id}/comments")
async def list_comments(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    comments = (
        db.query(DashboardComment)
        .filter(DashboardComment.dashboard_id == dashboard_id)
        .order_by(DashboardComment.created_at.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "dashboard_id": c.dashboard_id,
            "user_id": c.user_id,
            "parent_id": c.parent_id,
            "content": c.content,
            "chart_index": c.chart_index,
            "position_x": c.position_x,
            "position_y": c.position_y,
            "is_resolved": c.is_resolved,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if getattr(c, "updated_at", None) else None,
        }
        for c in comments
    ]


@router.post("/{dashboard_id}/comments", status_code=http_status.HTTP_201_CREATED)
async def create_comment(
    dashboard_id: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)

    # Validate parent exists if provided
    if payload.parent_id:
        _get_comment_or_404(payload.parent_id, dashboard_id, db)

    comment = DashboardComment(
        dashboard_id=dashboard_id,
        user_id=current_user["sub"],
        parent_id=payload.parent_id,
        content=payload.content,
        chart_index=payload.chart_index,
        position_x=payload.position_x,
        position_y=payload.position_y,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {
        "id": comment.id,
        "dashboard_id": comment.dashboard_id,
        "user_id": comment.user_id,
        "parent_id": comment.parent_id,
        "content": comment.content,
        "chart_index": comment.chart_index,
        "position_x": comment.position_x,
        "position_y": comment.position_y,
        "is_resolved": comment.is_resolved,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.put("/{dashboard_id}/comments/{comment_id}")
async def update_comment(
    dashboard_id: str,
    comment_id: str,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    comment = _get_comment_or_404(comment_id, dashboard_id, db)
    if comment.user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Cannot edit another user's comment")
    comment.content = payload.content
    if hasattr(comment, "updated_at"):
        comment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(comment)
    return {"id": comment.id, "content": comment.content}


@router.delete("/{dashboard_id}/comments/{comment_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_comment(
    dashboard_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    comment = _get_comment_or_404(comment_id, dashboard_id, db)
    if comment.user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")
    db.delete(comment)
    db.commit()


@router.post("/{dashboard_id}/comments/{comment_id}/resolve")
async def resolve_comment(
    dashboard_id: str,
    comment_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    comment = _get_comment_or_404(comment_id, dashboard_id, db)
    comment.is_resolved = not comment.is_resolved
    db.commit()
    return {"id": comment.id, "is_resolved": comment.is_resolved}


# ── Version history ───────────────────────────────────────────────

@router.get("/{dashboard_id}/versions")
async def list_versions(
    dashboard_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    versions = (
        db.query(DashboardVersion)
        .filter(DashboardVersion.dashboard_id == dashboard_id)
        .order_by(DashboardVersion.version_number.desc())
        .all()
    )
    return [
        {
            "version_number": v.version_number,
            "title": v.title,
            "chart_count": len(v.charts) if v.charts else 0,
            "created_by": v.created_by,
            "change_summary": v.change_summary,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


@router.get("/{dashboard_id}/versions/{version_number}")
async def get_version(
    dashboard_id: str,
    version_number: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    version = db.query(DashboardVersion).filter(
        DashboardVersion.dashboard_id == dashboard_id,
        DashboardVersion.version_number == version_number,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "version_number": version.version_number,
        "title": version.title,
        "layout": version.layout,
        "charts": version.charts,
        "created_by": version.created_by,
        "change_summary": version.change_summary,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


@router.post("/{dashboard_id}/versions/{version_number}/restore")
async def restore_version(
    dashboard_id: str,
    version_number: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Restore a dashboard to a previous version snapshot."""
    dashboard = _get_dashboard_or_404(dashboard_id, current_user["sub"], db)
    version = db.query(DashboardVersion).filter(
        DashboardVersion.dashboard_id == dashboard_id,
        DashboardVersion.version_number == version_number,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Snapshot current state before restoring
    _snapshot(
        dashboard,
        created_by=current_user["sub"],
        change_summary=f"Auto-saved before restoring v{version_number}",
        db=db,
    )

    dashboard.title = version.title
    dashboard.layout = version.layout
    dashboard.charts = version.charts
    if hasattr(dashboard, "updated_at"):
        dashboard.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dashboard)
    return {
        "message": f"Dashboard restored to version {version_number}",
        "dashboard": _dashboard_dict(dashboard),
    }


# ─── Phase 17: PR Review Workflow ─────────────────────────────

class ProposeChangeRequest(BaseModel):
    title: str
    description: Optional[str] = None
    proposed_layout: Optional[dict] = None
    proposed_charts: Optional[list] = None
    source_session_id: Optional[str] = None


@router.post("/{dashboard_id}/propose-change")
async def propose_change(
    dashboard_id: str,
    payload: ProposeChangeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Propose a change to a shared dashboard — requires peer approval before publishing."""
    from models.database import DashboardPR
    uid = current_user.get("sub") or current_user.get("id")
    dashboard = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Build diff summary
    diff_summary = {}
    if payload.proposed_charts and dashboard.charts:
        diff_summary["charts_changed"] = len(payload.proposed_charts) != len(dashboard.charts)
        diff_summary["charts_count"] = {"before": len(dashboard.charts or []), "after": len(payload.proposed_charts)}
    if payload.proposed_layout and dashboard.layout:
        diff_summary["layout_changed"] = payload.proposed_layout != dashboard.layout

    pr = DashboardPR(
        dashboard_id=dashboard_id,
        proposed_by=uid,
        title=payload.title,
        description=payload.description,
        proposed_layout=payload.proposed_layout,
        proposed_charts=payload.proposed_charts,
        diff_summary=diff_summary,
        source_session_id=payload.source_session_id,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return {
        "pr_id": pr.id,
        "status": "pending",
        "message": "Change proposed. Awaiting review.",
    }


@router.get("/{dashboard_id}/reviews")
async def list_reviews(
    dashboard_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all proposed changes (PRs) for a dashboard."""
    from models.database import DashboardPR
    prs = db.query(DashboardPR).filter(
        DashboardPR.dashboard_id == dashboard_id
    ).order_by(DashboardPR.created_at.desc()).all()
    return [
        {
            "id": pr.id,
            "dashboard_id": pr.dashboard_id,
            "proposed_by": pr.proposed_by,
            "title": pr.title,
            "description": pr.description,
            "status": pr.status,
            "reviewed_by": pr.reviewed_by,
            "review_comment": pr.review_comment,
            "reviewed_at": pr.reviewed_at,
            "diff_summary": pr.diff_summary,
            "created_at": pr.created_at,
        }
        for pr in prs
    ]


@router.post("/{dashboard_id}/reviews/{pr_id}/approve")
async def approve_pr(
    dashboard_id: str,
    pr_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a proposed dashboard change — applies it immediately."""
    from models.database import DashboardPR
    from datetime import datetime
    uid = current_user.get("sub") or current_user.get("id")
    pr = db.query(DashboardPR).filter(
        DashboardPR.id == pr_id,
        DashboardPR.dashboard_id == dashboard_id,
        DashboardPR.status == "pending",
    ).first()
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found or already reviewed")
    dashboard = db.query(Dashboard).filter(Dashboard.id == dashboard_id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    # Apply the changes
    if pr.proposed_layout:
        dashboard.layout = pr.proposed_layout
    if pr.proposed_charts:
        dashboard.charts = pr.proposed_charts
    dashboard.updated_at = datetime.utcnow()

    pr.status = "approved"
    pr.reviewed_by = uid
    pr.reviewed_at = datetime.utcnow()
    db.commit()
    return {"status": "approved", "message": "Dashboard updated successfully."}


@router.post("/{dashboard_id}/reviews/{pr_id}/reject")
async def reject_pr(
    dashboard_id: str,
    pr_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a proposed dashboard change."""
    from models.database import DashboardPR
    from datetime import datetime
    uid = current_user.get("sub") or current_user.get("id")
    pr = db.query(DashboardPR).filter(
        DashboardPR.id == pr_id,
        DashboardPR.dashboard_id == dashboard_id,
        DashboardPR.status == "pending",
    ).first()
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found or already reviewed")
    pr.status = "rejected"
    pr.reviewed_by = uid
    pr.review_comment = payload.get("comment", "")
    pr.reviewed_at = datetime.utcnow()
    db.commit()
    return {"status": "rejected"}
