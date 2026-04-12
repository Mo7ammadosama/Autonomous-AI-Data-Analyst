"""
Root Cause Analysis Router — explain WHY a metric changed.
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Dataset, RCAResult
from services.data_processor import load_dataset
from services.root_cause import rca_analyzer
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────

class RCARequest(BaseModel):
    dataset_id: str
    metric_column: str
    date_column: Optional[str] = None
    comparison_period: str = "month"   # week | month | quarter


# ── Background task ───────────────────────────────────────────────

def _run_rca(rca_id: str, dataset_file_path: str, dataset_file_type: str,
             metric_column: str, date_column: Optional[str],
             comparison_period: str, dataset_id: str, user_id: str):
    """Run RCA in background and persist result to DB."""
    from models.database import SessionLocal
    db = SessionLocal()
    try:
        rca = db.query(RCAResult).filter(RCAResult.id == rca_id).first()
        if not rca:
            return

        rca.status = "running"
        db.commit()

        df = load_dataset(dataset_file_path, dataset_file_type)
        result = rca_analyzer.analyze(df, metric_column, date_column, comparison_period)

        rca.status = "done"
        rca.change_pct = result["change_pct"]
        rca.confidence = result["confidence"]
        rca.result_data = {
            "top_drivers": result["top_drivers"],
            "segments": result["segments"],
        }
        rca.narrative = result["narrative"]
        rca.chart = result["chart"]
        db.commit()
    except Exception as e:
        logger.error(f"RCA background task failed: {e}")
        rca = db.query(RCAResult).filter(RCAResult.id == rca_id).first()
        if rca:
            rca.status = "error"
            rca.error_message = str(e)
            db.commit()
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze(
    req: RCARequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Start a Root Cause Analysis job (runs in background)."""
    dataset = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    # Verify access: must own the dataset or be in same workspace
    user_id = current_user["sub"]
    if dataset.owner_id != user_id and dataset.workspace_id != current_user.get("workspace_id"):
        raise HTTPException(status_code=403, detail="Access denied to this dataset")

    if req.metric_column not in (dataset.columns_meta or {}):
        # Validate by loading — might be expensive; skip for speed
        pass

    rca_id = str(uuid.uuid4())
    rca = RCAResult(
        id=rca_id,
        user_id=current_user["sub"],
        dataset_id=req.dataset_id,
        metric_column=req.metric_column,
        date_column=req.date_column,
        comparison_period=req.comparison_period,
        status="pending",
    )
    db.add(rca)
    db.commit()

    background_tasks.add_task(
        _run_rca,
        rca_id,
        dataset.file_path,
        dataset.file_type,
        req.metric_column,
        req.date_column,
        req.comparison_period,
        req.dataset_id,
        current_user["sub"],
    )

    return {"rca_id": rca_id, "status": "pending", "message": "RCA started — poll /history or /{id} for results"}


@router.get("/history")
async def get_history(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all RCA runs for the current user."""
    results = (
        db.query(RCAResult)
        .filter(RCAResult.user_id == current_user["sub"])
        .order_by(RCAResult.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "dataset_id": r.dataset_id,
            "metric_column": r.metric_column,
            "comparison_period": r.comparison_period,
            "change_pct": r.change_pct,
            "confidence": r.confidence,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in results
    ]


@router.get("/{rca_id}")
async def get_rca(
    rca_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full RCA result by ID."""
    rca = db.query(RCAResult).filter(
        RCAResult.id == rca_id,
        RCAResult.user_id == current_user["sub"],
    ).first()
    if not rca:
        raise HTTPException(status_code=404, detail="RCA result not found")

    return {
        "id": rca.id,
        "dataset_id": rca.dataset_id,
        "metric_column": rca.metric_column,
        "date_column": rca.date_column,
        "comparison_period": rca.comparison_period,
        "change_pct": rca.change_pct,
        "confidence": rca.confidence,
        "status": rca.status,
        "narrative": rca.narrative,
        "chart": rca.chart,
        "result_data": rca.result_data,
        "error_message": rca.error_message,
        "created_at": rca.created_at.isoformat() if rca.created_at else None,
    }


@router.post("/{rca_id}/regenerate")
async def regenerate_rca(
    rca_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Re-run an existing RCA with the same parameters on updated data."""
    rca = db.query(RCAResult).filter(
        RCAResult.id == rca_id,
        RCAResult.user_id == current_user["sub"],
    ).first()
    if not rca:
        raise HTTPException(status_code=404, detail="RCA result not found")

    dataset = db.query(Dataset).filter(Dataset.id == rca.dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset no longer exists")

    rca.status = "pending"
    rca.error_message = None
    db.commit()

    background_tasks.add_task(
        _run_rca,
        rca_id,
        dataset.file_path,
        dataset.file_type,
        rca.metric_column,
        rca.date_column,
        rca.comparison_period,
        rca.dataset_id,
        current_user["sub"],
    )
    return {"rca_id": rca_id, "status": "pending", "message": "RCA re-queued"}
