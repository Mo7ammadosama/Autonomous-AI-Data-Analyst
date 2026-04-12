"""
Domain Templates Router

GET  /api/domain-templates                        → list all templates (summary)
GET  /api/domain-templates/{domain}               → list templates for a domain
GET  /api/domain-templates/{domain}/{template_name} → full template detail
POST /api/domain-templates/detect                 → auto-detect domain from dataset columns
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import Dataset, get_db
from security.auth import get_current_user
from services.domain_templates import (
    DOMAIN_TEMPLATES,
    detect_domain,
    get_all_templates,
    get_template,
    get_templates_by_domain,
)

router = APIRouter(prefix="/api/domain-templates", tags=["Domain Templates"])


# ─────────────────────────────────────────────────────────────────────────────
#  Schemas
# ─────────────────────────────────────────────────────────────────────────────

class TemplateSummary(BaseModel):
    domain: str
    name: str
    description: str
    required_columns: list[str]


class DetectRequest(BaseModel):
    dataset_id: Optional[str] = None
    columns: Optional[list[str]] = None


class DetectResponse(BaseModel):
    domain: str
    template_name: str
    confidence: float
    template: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
#  Routes — specific BEFORE parameterized
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TemplateSummary])
def list_all_templates(current_user=Depends(get_current_user)):
    """List all domain templates (summary only)."""
    return get_all_templates()


@router.post("/detect", response_model=DetectResponse)
def detect_template(
    req: DetectRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Auto-detect the best-matching domain template from a dataset's columns
    or from an explicit column list.
    """
    columns: list[str] = []

    if req.columns:
        columns = req.columns
    elif req.dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        try:
            import pandas as pd
            df = pd.read_csv(dataset.file_path, nrows=1)
            columns = df.columns.tolist()
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not read dataset columns: {exc}")
    else:
        raise HTTPException(status_code=422, detail="Provide dataset_id or columns list")

    domain, template_name, confidence = detect_domain(columns)
    template = get_template(domain, template_name) if confidence > 0 else None

    return DetectResponse(
        domain=domain,
        template_name=template_name,
        confidence=confidence,
        template=template,
    )


@router.get("/{domain}", response_model=dict)
def get_domain_templates(domain: str, current_user=Depends(get_current_user)):
    """Return all templates for a specific domain."""
    templates = get_templates_by_domain(domain)
    if templates is None:
        raise HTTPException(
            status_code=404,
            detail=f"Domain '{domain}' not found. Available: {list(DOMAIN_TEMPLATES.keys())}",
        )
    return templates


@router.get("/{domain}/{template_name}", response_model=dict)
def get_single_template(
    domain: str,
    template_name: str,
    current_user=Depends(get_current_user),
):
    """Return the full detail of a single domain template."""
    template = get_template(domain, template_name)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{domain}/{template_name}' not found",
        )
    return template
