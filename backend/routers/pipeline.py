"""
Auto-Pipeline Router
GET  /api/pipeline/{dataset_id}        — get pipeline results
POST /api/pipeline/{dataset_id}/run    — (re)run pipeline manually
GET  /api/pipeline/{dataset_id}/story  — data story only
GET  /api/pipeline/{dataset_id}/recommendations — recommendations only
GET  /api/pipeline/{dataset_id}/anomalies       — anomalies only
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import logging

from models.database import get_db, Dataset
from services.auto_pipeline import run_pipeline, get_pipeline_result
from services.llm_service import LLMService
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

_llm = LLMService()


def _get_dataset_or_404(dataset_id: str, current_user: dict, db: Session) -> Dataset:
    ds = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"]
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.get("/{dataset_id}")
async def get_pipeline(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retrieve full pipeline results for a dataset."""
    _get_dataset_or_404(dataset_id, current_user, db)
    result = get_pipeline_result(dataset_id, db)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Pipeline not run yet. POST to /api/pipeline/{dataset_id}/run to start."
        )
    return result


@router.post("/{dataset_id}/run")
async def trigger_pipeline(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Trigger (or re-run) the auto-analysis pipeline in background."""
    _get_dataset_or_404(dataset_id, current_user, db)
    background_tasks.add_task(_run_pipeline_bg, dataset_id)
    return {"message": "Pipeline started. Fetch results at GET /api/pipeline/{dataset_id}", "status": "running"}


def _run_pipeline_bg(dataset_id: str):
    """Background task wrapper — creates its own DB session."""
    from models.database import SessionLocal
    db = SessionLocal()
    try:
        run_pipeline(dataset_id, db, llm_service=_llm)
    finally:
        db.close()


@router.get("/{dataset_id}/story")
async def get_story(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the data narrative story for a dataset."""
    _get_dataset_or_404(dataset_id, current_user, db)
    result = get_pipeline_result(dataset_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Pipeline not run yet.")
    return {"story": result.get("story", ""), "dataset_id": dataset_id}


@router.get("/{dataset_id}/recommendations")
async def get_recommendations(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get business recommendations for a dataset."""
    _get_dataset_or_404(dataset_id, current_user, db)
    result = get_pipeline_result(dataset_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Pipeline not run yet.")
    return {
        "recommendations": result.get("recommendations", []),
        "dataset_id": dataset_id,
    }


@router.get("/{dataset_id}/anomalies")
async def get_anomalies(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get anomaly detection results for a dataset."""
    _get_dataset_or_404(dataset_id, current_user, db)
    result = get_pipeline_result(dataset_id, db)
    if not result:
        # Run anomaly detection on the fly
        from models.database import Dataset
        from services.data_processor import load_dataset
        from services.anomaly_detector import detect_anomalies
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
        try:
            df = load_dataset(ds.file_path, ds.file_type)
            anomalies = detect_anomalies(df)
            return {"anomalies": anomalies, "dataset_id": dataset_id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"anomalies": result.get("anomalies", {}), "dataset_id": dataset_id}
