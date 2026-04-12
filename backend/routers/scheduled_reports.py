"""
Scheduled Reports Router — CRUD + trigger for automated PDF email reports.

Endpoints:
  POST   /api/scheduled-reports/                Create schedule
  GET    /api/scheduled-reports/                List schedules
  GET    /api/scheduled-reports/{id}            Get schedule
  PUT    /api/scheduled-reports/{id}            Update schedule
  DELETE /api/scheduled-reports/{id}            Delete schedule
  POST   /api/scheduled-reports/{id}/send-now   Trigger immediately
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from models.database import get_db, ScheduledReport, Dataset
from security.auth import get_current_user
from services.scheduled_reports import compute_next_run

logger = logging.getLogger(__name__)
router = APIRouter()

FREQUENCIES = {"daily", "weekly", "monthly"}


class ReportCreate(BaseModel):
    dataset_id: str
    title: str
    frequency: str = "weekly"
    email_recipient: str


class ReportUpdate(BaseModel):
    title: Optional[str] = None
    frequency: Optional[str] = None
    email_recipient: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize(r: ScheduledReport) -> dict:
    return {
        "id": r.id,
        "dataset_id": r.dataset_id,
        "title": r.title,
        "frequency": r.frequency,
        "email_recipient": r.email_recipient,
        "is_active": r.is_active,
        "last_sent": r.last_sent.isoformat() if r.last_sent else None,
        "next_run": r.next_run.isoformat() if r.next_run else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ReportCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.frequency not in FREQUENCIES:
        raise HTTPException(status_code=400, detail=f"frequency must be one of {FREQUENCIES}")

    dataset = db.query(Dataset).filter(
        Dataset.id == payload.dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    report = ScheduledReport(
        user_id=current_user["sub"],
        dataset_id=payload.dataset_id,
        title=payload.title,
        frequency=payload.frequency,
        email_recipient=payload.email_recipient,
        next_run=compute_next_run(payload.frequency),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _serialize(report)


@router.get("/")
async def list_schedules(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reports = db.query(ScheduledReport).filter(
        ScheduledReport.user_id == current_user["sub"]
    ).order_by(ScheduledReport.created_at.desc()).all()
    return [_serialize(r) for r in reports]


@router.get("/{report_id}")
async def get_schedule(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(ScheduledReport).filter(
        ScheduledReport.id == report_id,
        ScheduledReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    return _serialize(report)


@router.put("/{report_id}")
async def update_schedule(
    report_id: str,
    payload: ReportUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(ScheduledReport).filter(
        ScheduledReport.id == report_id,
        ScheduledReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Scheduled report not found")

    if payload.frequency and payload.frequency not in FREQUENCIES:
        raise HTTPException(status_code=400, detail=f"frequency must be one of {FREQUENCIES}")

    for field in ("title", "frequency", "email_recipient", "is_active"):
        val = getattr(payload, field)
        if val is not None:
            setattr(report, field, val)

    if payload.frequency:
        report.next_run = compute_next_run(payload.frequency)

    db.commit()
    db.refresh(report)
    return _serialize(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(ScheduledReport).filter(
        ScheduledReport.id == report_id,
        ScheduledReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Scheduled report not found")
    db.delete(report)
    db.commit()


@router.post("/{report_id}/send-now")
async def send_now(
    report_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Trigger a scheduled report immediately (sends in background)."""
    report = db.query(ScheduledReport).filter(
        ScheduledReport.id == report_id,
        ScheduledReport.user_id == current_user["sub"],
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Scheduled report not found")

    def _send():
        from models.database import SessionLocal
        from services.scheduled_reports import _generate_pdf_bytes, send_report_email
        import asyncio
        _db = SessionLocal()
        try:
            pdf = _generate_pdf_bytes(report.dataset_id, report.title, _db)
            asyncio.run(send_report_email(
                report.email_recipient,
                f"[DataMind] Report: {report.title}",
                f"<html><body><h2>Report: {report.title}</h2><p>Attached.</p></body></html>",
                pdf,
                f"{report.title.replace(' ','_')}.pdf",
            ))
            rpt = _db.query(ScheduledReport).filter(ScheduledReport.id == report_id).first()
            if rpt:
                rpt.last_sent = datetime.utcnow()
                _db.commit()
        except Exception as e:
            logger.error(f"send-now failed: {e}")
        finally:
            _db.close()

    background_tasks.add_task(_send)
    return {"status": "queued", "report_id": report_id, "email": report.email_recipient}
