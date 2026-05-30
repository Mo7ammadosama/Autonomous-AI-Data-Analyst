"""
Custom Reports Router

POST /api/custom-reports               → create
GET  /api/custom-reports               → list
GET  /api/custom-reports/{id}          → get
PUT  /api/custom-reports/{id}          → update sections
POST /api/custom-reports/{id}/generate → AI fills all sections
GET  /api/custom-reports/{id}/export   → export as PDF or HTML
DELETE /api/custom-reports/{id}        → delete
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.database import CustomReport, Dataset, get_db
from security.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/custom-reports", tags=["Custom Reports"])


# ─────────────────────────────────────────────────────────────────────────────
#  Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SectionDef(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "text"           # text | chart | table | metric_card | insight_list
    title: str
    content: Optional[Any] = None
    order: int = 0


class CreateReportRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    domain: Optional[str] = None
    template_name: Optional[str] = None
    dataset_id: Optional[str] = None
    connection_id: Optional[str] = None
    sections: list[SectionDef] = []


class UpdateReportRequest(BaseModel):
    name: Optional[str] = None
    sections: Optional[list[SectionDef]] = None
    domain: Optional[str] = None
    template_name: Optional[str] = None


class ReportOut(BaseModel):
    id: str
    name: str
    domain: Optional[str]
    template_name: Optional[str]
    dataset_id: Optional[str]
    connection_id: Optional[str]
    sections: list[dict]
    generated_content: dict
    status: str
    pdf_path: Optional[str]
    created_at: str
    updated_at: str


class ReportListItem(BaseModel):
    id: str
    name: str
    domain: Optional[str]
    template_name: Optional[str]
    status: str
    created_at: str


# ─────────────────────────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────────────────────────

def _report_to_out(r: CustomReport) -> ReportOut:
    return ReportOut(
        id=r.id,
        name=r.name,
        domain=r.domain,
        template_name=r.template_name,
        dataset_id=r.dataset_id,
        connection_id=r.connection_id,
        sections=r.sections or [],
        generated_content=r.generated_content or {},
        status=r.status,
        pdf_path=r.pdf_path,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat(),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Routes — specific BEFORE parameterized
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=ReportOut, status_code=201)
def create_report(
    req: CreateReportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new custom report."""
    if req.dataset_id:
        ds = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
        if not ds:
            req.dataset_id = None  # dataset not found — create report without it

    # If a template was specified and no sections provided, pre-populate from template
    sections = [s.model_dump() for s in req.sections]
    if not sections and req.domain and req.template_name:
        from services.domain_templates import get_template
        tmpl = get_template(req.domain, req.template_name)
        if tmpl:
            sections = [
                {
                    "id": str(uuid.uuid4()),
                    "type": "text",
                    "title": sec_name,
                    "content": None,
                    "order": idx,
                }
                for idx, sec_name in enumerate(tmpl.get("report_sections", []))
            ]

    report = CustomReport(
        id=str(uuid.uuid4()),
        user_id=current_user["sub"],
        name=req.name,
        domain=req.domain,
        template_name=req.template_name,
        dataset_id=req.dataset_id,
        connection_id=req.connection_id,
        sections=sections,
        generated_content={},
        status="draft",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_to_out(report)


@router.get("", response_model=list[ReportListItem])
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List the current user's custom reports."""
    reports = (
        db.query(CustomReport)
        .filter(CustomReport.user_id == current_user["sub"])
        .order_by(CustomReport.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        ReportListItem(
            id=r.id,
            name=r.name,
            domain=r.domain,
            template_name=r.template_name,
            status=r.status,
            created_at=r.created_at.isoformat(),
        )
        for r in reports
    ]


@router.post("/{report_id}/generate", response_model=ReportOut)
def generate_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """AI fills all empty report sections using OpenAI."""
    report = db.query(CustomReport).filter(
        CustomReport.id == report_id,
        CustomReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = "generating"
    db.commit()

    try:
        generated = _ai_generate_sections(report, db)
        report.generated_content = generated
        report.status = "ready"
    except Exception as exc:
        logger.error(f"Report generation failed: {exc}", exc_info=True)
        report.status = "failed"
        report.generated_content = {"error": str(exc)}

    db.commit()
    db.refresh(report)
    return _report_to_out(report)


@router.get("/{report_id}/export")
def export_report(
    report_id: str,
    fmt: str = Query("html", regex="^(pdf|html|json)$"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export a report as PDF, HTML, or JSON."""
    report = db.query(CustomReport).filter(
        CustomReport.id == report_id,
        CustomReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    from services.report_builder import BuiltReport, ReportBuilder, ReportSection

    # Build section objects; use generated_content to fill in content
    gen = report.generated_content or {}
    sections = []
    for s in (report.sections or []):
        content = s.get("content") or gen.get(s.get("id", "")) or {"body": ""}
        sections.append(ReportSection(
            id=s.get("id", str(uuid.uuid4())),
            type=s.get("type", "text"),
            title=s.get("title", "Section"),
            content=content,
            order=s.get("order", 0),
        ))

    built = BuiltReport(
        name=report.name,
        domain=report.domain,
        sections=sections,
    )
    builder = ReportBuilder(built)

    if fmt == "json":
        return Response(
            content=builder.to_json(),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{report.name}.json"'},
        )
    elif fmt == "html":
        return Response(
            content=builder.to_html(),
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{report.name}.html"'},
        )
    elif fmt == "pdf":
        try:
            pdf_bytes = builder.to_pdf_bytes()
        except RuntimeError as exc:
            raise HTTPException(status_code=501, detail=str(exc))
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{report.name}.pdf"'},
        )


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a single custom report with all sections and generated content."""
    report = db.query(CustomReport).filter(
        CustomReport.id == report_id,
        CustomReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_to_out(report)


@router.put("/{report_id}", response_model=ReportOut)
def update_report(
    report_id: str,
    req: UpdateReportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update report name, domain, template, or sections order/content."""
    report = db.query(CustomReport).filter(
        CustomReport.id == report_id,
        CustomReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if req.name is not None:
        report.name = req.name
    if req.domain is not None:
        report.domain = req.domain
    if req.template_name is not None:
        report.template_name = req.template_name
    if req.sections is not None:
        report.sections = [s.model_dump() for s in req.sections]
    report.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(report)
    return _report_to_out(report)


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a custom report."""
    report = db.query(CustomReport).filter(
        CustomReport.id == report_id,
        CustomReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Remove PDF if exists
    if report.pdf_path and os.path.exists(report.pdf_path):
        try:
            os.remove(report.pdf_path)
        except OSError:
            pass

    db.delete(report)
    db.commit()
    return {"message": "Report deleted"}


# ─────────────────────────────────────────────────────────────────────────────
#  AI generation helper
# ─────────────────────────────────────────────────────────────────────────────

def _ai_generate_sections(report: CustomReport, db: Session) -> dict:
    """
    Fill each report section with AI-generated content via llm_router.
    Routes to the best available provider (Anthropic, OpenAI, etc.).
    Returns {section_id: {"body": "<markdown>"}}
    """
    import os
    from services.llm_router import llm_router

    # Build context about dataset if available
    dataset_context = ""
    if report.dataset_id:
        try:
            import pandas as pd
            dataset = db.query(Dataset).filter(Dataset.id == report.dataset_id).first()
            if dataset and os.path.exists(dataset.file_path):
                df = pd.read_csv(dataset.file_path, nrows=5)
                dataset_context = (
                    f"\nDataset: {dataset.name}\n"
                    f"Columns: {df.columns.tolist()}\n"
                    f"Rows: {dataset.row_count}\n"
                    f"Sample:\n{df.head(3).to_string()}\n"
                )
        except Exception as exc:
            logger.warning(f"Could not read dataset for report generation: {exc}")

    # Build template context
    template_context = ""
    if report.domain and report.template_name:
        from services.domain_templates import get_template
        tmpl = get_template(report.domain, report.template_name)
        if tmpl:
            template_context = (
                f"\nAnalysis template: {tmpl['name']}\n"
                f"Description: {tmpl['description']}\n"
                f"KPIs: {json.dumps(tmpl.get('kpis', []))}\n"
                f"Sample insights: {tmpl.get('sample_insights', [])}\n"
            )

    system_prompt = (
        "You are a professional data analyst writing a business report. "
        "Write in professional markdown, be specific and data-driven (150–300 words). "
        "If real data is unavailable, use realistic placeholder values in [brackets]."
    )

    generated: dict[str, Any] = {}

    for section in (report.sections or []):
        section_id = section.get("id", "")
        section_title = section.get("title", "Section")
        section_type = section.get("type", "text")

        if section_type != "text":
            # Non-text sections are populated by code/charts, not LLM
            continue

        user_prompt = (
            f"Report name: {report.name}\n"
            f"Domain: {report.domain or 'general'}\n"
            f"{dataset_context}"
            f"{template_context}"
            f"\nWrite the '{section_title}' section of this report."
        )

        try:
            body = llm_router.complete(
                system=system_prompt,
                user=user_prompt,
                max_tokens=600,
                task_type="report",
            )
        except Exception as exc:
            body = f"*[Generation failed: {exc}]*"

        generated[section_id] = {"body": body}

    return generated
