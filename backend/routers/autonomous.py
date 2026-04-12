"""
Autonomous Data Analyst Router
POST /api/autonomous/analyze  — run full analysis suite
GET  /api/autonomous/{dataset_id}/status — get latest result
"""

import logging
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Dataset
from security.auth import get_current_user
from services.llm_service import LLMService
from services.autonomous_pipeline import run_autonomous_analysis

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory job cache: dataset_id → result dict
_job_cache: dict = {}


class AnalyzeRequest(BaseModel):
    dataset_id: str


def _run_in_background(dataset_id: str, owner_id: str, db_url: str):
    """Run autonomous analysis in a background thread with its own DB session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        llm = LLMService()
        result = run_autonomous_analysis(dataset_id, db, owner_id, llm)
        _job_cache[dataset_id] = result
    except Exception as e:
        _job_cache[dataset_id] = {"pipeline_status": "error", "errors": [str(e)]}
    finally:
        db.close()


@router.post("/analyze")
async def start_autonomous_analysis(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start autonomous analysis for a dataset.
    Returns immediately with status='started'.
    Poll GET /api/autonomous/{dataset_id}/status for results.
    """
    dataset = db.query(Dataset).filter(
        Dataset.id == request.dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.status != "ready":
        raise HTTPException(status_code=400, detail=f"Dataset not ready (status={dataset.status})")

    # Mark as running in cache immediately
    _job_cache[request.dataset_id] = {
        "dataset_id": request.dataset_id,
        "dataset_name": dataset.name,
        "pipeline_status": "running",
        "stages_completed": [],
    }

    # Get the database URL for the background thread
    from models.database import engine as db_engine
    db_url = str(db_engine.url)

    # Run in background thread
    thread = threading.Thread(
        target=_run_in_background,
        args=(request.dataset_id, current_user["sub"], db_url),
        daemon=True,
    )
    thread.start()

    return {
        "status": "started",
        "dataset_id": request.dataset_id,
        "message": f"Autonomous analysis started for '{dataset.name}'. Poll /status for results.",
    }


@router.get("/{dataset_id}/status")
async def get_analysis_status(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the current status / result of an autonomous analysis job.
    """
    # Verify ownership
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset_id not in _job_cache:
        # Try to load from pipeline result table (previous run)
        from services.auto_pipeline import get_pipeline_result
        pr = get_pipeline_result(dataset_id, db)
        if pr and pr["status"] == "done":
            return {"pipeline_status": "complete", **pr}
        return {"pipeline_status": "not_started", "dataset_id": dataset_id}

    return _job_cache[dataset_id]


@router.delete("/{dataset_id}/cache")
async def clear_cache(
    dataset_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clear cached result so analysis can be re-run."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _job_cache.pop(dataset_id, None)
    return {"status": "cleared"}
