"""
Dashboard Templates Router

Endpoints (static paths BEFORE /{id}):
  GET  /api/templates/industries          List distinct industries
  GET  /api/templates/featured            List featured templates
  GET  /api/templates/                    List / search templates
  GET  /api/templates/{id}               Get single template
  POST /api/templates/{id}/use           Instantiate template → Dashboard
  POST /api/templates/                   Create template (admin)
"""

import logging
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, DashboardTemplate, Dataset
from security.auth import get_current_user
from services.template_service import template_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    tags: Optional[List[str]] = None
    thumbnail_url: Optional[str] = None
    layout: Optional[Dict] = None
    charts_config: Optional[List] = None
    column_mappings: Optional[Dict] = None
    is_featured: bool = False


class UseTemplateRequest(BaseModel):
    dataset_id: str
    column_mappings: Optional[Dict[str, str]] = None


# ── Serializer ────────────────────────────────────────────────────

def _template_dict(t: DashboardTemplate, include_config: bool = False) -> dict:
    d = {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "industry": t.industry,
        "tags": t.tags or [],
        "thumbnail_url": t.thumbnail_url,
        "is_featured": t.is_featured,
        "usage_count": t.usage_count or 0,
        "column_mappings": t.column_mappings or {},
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if include_config:
        d["charts_config"] = t.charts_config or []
        d["layout"] = t.layout or {}
    return d


# ── Static endpoints (MUST be before /{id}) ───────────────────────

@router.get("/industries")
async def list_industries(db: Session = Depends(get_db)):
    """Return distinct industry values across all templates."""
    rows = db.query(DashboardTemplate.industry).distinct().all()
    return sorted(set(r[0] for r in rows if r[0]))


@router.get("/featured")
async def list_featured(db: Session = Depends(get_db)):
    """Return featured templates."""
    templates = (
        db.query(DashboardTemplate)
        .filter(DashboardTemplate.is_featured == True)
        .order_by(DashboardTemplate.usage_count.desc())
        .all()
    )
    return [_template_dict(t) for t in templates]


# ── Collection endpoints ──────────────────────────────────────────

_SEED_TEMPLATES = [
    {"name": "Revenue Performance Dashboard", "industry": "Finance",    "description": "KPI cards + revenue trend + regional breakdown. Board-ready in seconds.",              "is_featured": True,  "usage_count": 4821, "tags": ["revenue", "KPI", "trend"]},
    {"name": "Sales Pipeline Overview",        "industry": "Sales",      "description": "Pipeline funnel, win-rate, deal velocity, and rep leaderboard.",                       "is_featured": True,  "usage_count": 3654, "tags": ["pipeline", "CRM", "forecast"]},
    {"name": "Customer Churn Analysis",        "industry": "Sales",      "description": "Churn rate trend, cohort retention, at-risk customer heatmap.",                       "is_featured": True,  "usage_count": 3102, "tags": ["churn", "retention", "cohort"]},
    {"name": "Marketing Campaign ROI",         "industry": "Marketing",  "description": "Multi-channel attribution, ROAS by channel, CPL and CPA trends.",                    "is_featured": True,  "usage_count": 2987, "tags": ["ROI", "attribution", "campaigns"]},
    {"name": "P&L Executive Summary",          "industry": "Finance",    "description": "Gross margin, EBITDA, YoY variance — formatted for board presentation.",              "is_featured": False, "usage_count": 2541, "tags": ["P&L", "EBITDA", "margin"]},
    {"name": "Inventory & Supply Chain",       "industry": "Operations", "description": "Inventory turnover, stockout risk, supplier on-time delivery, carrying cost.",        "is_featured": False, "usage_count": 2198, "tags": ["inventory", "supply chain", "logistics"]},
    {"name": "HR Workforce Analytics",         "industry": "HR",         "description": "Headcount, attrition, time-to-hire, performance distribution, salary equity.",       "is_featured": False, "usage_count": 1876, "tags": ["headcount", "attrition", "workforce"]},
    {"name": "E-commerce Funnel",              "industry": "Retail",     "description": "Session → cart → checkout → purchase funnel with drop-off analysis.",                "is_featured": True,  "usage_count": 3312, "tags": ["funnel", "conversion", "e-commerce"]},
    {"name": "SaaS Metrics Dashboard",         "industry": "Technology", "description": "MRR, ARR, NRR, churn, CAC payback, LTV — complete SaaS command center.",             "is_featured": True,  "usage_count": 4105, "tags": ["SaaS", "MRR", "ARR", "NRR"]},
    {"name": "Patient Outcomes Tracker",       "industry": "Healthcare", "description": "Patient satisfaction, readmission rates, length of stay, outcome trends.",            "is_featured": False, "usage_count": 1432, "tags": ["patient", "outcomes", "clinical"]},
    {"name": "Budget vs Actual Variance",      "industry": "Finance",    "description": "Department-level budget tracking with variance analysis and corrective action flags.", "is_featured": False, "usage_count": 2234, "tags": ["budget", "variance", "finance"]},
    {"name": "Product Usage Analytics",        "industry": "Technology", "description": "Feature adoption, DAU/MAU, session duration, power user segmentation.",               "is_featured": False, "usage_count": 1987, "tags": ["product", "DAU", "feature adoption"]},
]


def _ensure_seed_templates(db: Session) -> None:
    """Seed default templates if the table is empty (idempotent)."""
    count = db.query(DashboardTemplate).count()
    if count > 0:
        return
    import uuid as _uuid
    for t in _SEED_TEMPLATES:
        db.add(DashboardTemplate(
            id=str(_uuid.uuid4()),
            name=t["name"],
            description=t["description"],
            industry=t["industry"],
            tags=t["tags"],
            is_featured=t["is_featured"],
            usage_count=t["usage_count"],
            layout={},
            charts_config=[],
            column_mappings={},
        ))
    db.commit()


@router.get("/")
async def list_templates(
    industry: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List templates with optional industry filter and full-text search."""
    _ensure_seed_templates(db)
    q = db.query(DashboardTemplate)
    if industry:
        q = q.filter(DashboardTemplate.industry == industry)
    if search:
        q = q.filter(
            DashboardTemplate.name.ilike(f"%{search}%") |
            DashboardTemplate.description.ilike(f"%{search}%")
        )
    templates = q.order_by(DashboardTemplate.usage_count.desc()).all()
    return [_template_dict(t) for t in templates]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new dashboard template (admin use)."""
    tmpl = DashboardTemplate(
        name=payload.name,
        description=payload.description,
        industry=payload.industry,
        tags=payload.tags or [],
        thumbnail_url=payload.thumbnail_url,
        layout=payload.layout or {},
        charts_config=payload.charts_config or [],
        column_mappings=payload.column_mappings or {},
        is_featured=payload.is_featured,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return _template_dict(tmpl, include_config=True)


# ── Single-item endpoints ─────────────────────────────────────────

@router.get("/{template_id}")
async def get_template(
    template_id: str,
    db: Session = Depends(get_db),
):
    """Get full template details including charts_config."""
    tmpl = db.query(DashboardTemplate).filter(DashboardTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_dict(tmpl, include_config=True)


@router.post("/{template_id}/use", status_code=status.HTTP_201_CREATED)
async def use_template(
    template_id: str,
    payload: UseTemplateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Instantiate a template into a new Dashboard for the current user."""
    tmpl = db.query(DashboardTemplate).filter(DashboardTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    dataset = db.query(Dataset).filter(
        Dataset.id == payload.dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    dashboard = template_service.create_dashboard_from_template(
        template=tmpl,
        dataset_id=payload.dataset_id,
        user_id=current_user["sub"],
        column_mappings=payload.column_mappings,
        db=db,
    )
    return dashboard
