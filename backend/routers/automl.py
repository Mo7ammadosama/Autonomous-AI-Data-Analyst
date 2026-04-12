"""
AutoML Router — no-code ML model training and inference endpoints.
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, Dataset, AutoMLJob, AutoMLPrediction
from services.data_processor import load_dataset
from services.automl import automl_service
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────

class TrainRequest(BaseModel):
    dataset_id: str
    target_column: str
    task_type: str   # classification | regression | clustering


class PredictRequest(BaseModel):
    records: List[Dict[str, Any]]


# ── Background task ───────────────────────────────────────────────

def _run_automl_training(job_id: str, file_path: str, file_type: str,
                          target_column: str, task_type: str):
    """Run AutoML training in background and persist result."""
    from models.database import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(AutoMLJob).filter(AutoMLJob.id == job_id).first()
        if not job:
            return
        job.status = "training"
        db.commit()

        df = load_dataset(file_path, file_type)
        result = automl_service.train(df, target_column, task_type, job_id)

        job.status = "done"
        job.best_model = result.get("best_model")
        job.cv_score = result.get("cv_score")
        job.feature_importance = result.get("feature_importance")
        job.confusion_matrix = result.get("confusion_matrix")
        job.metrics = result.get("metrics") or {result.get("metric_name", "score"): result.get("cv_score")}
        job.result_data = {
            k: v for k, v in result.items()
            if k not in ("model_path", "feature_importance", "confusion_matrix", "metrics")
        }
        job.model_path = result.get("model_path")
        job.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"AutoML training failed for job {job_id}: {e}")
        job = db.query(AutoMLJob).filter(AutoMLJob.id == job_id).first()
        if job:
            job.status = "error"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/train")
async def train_model(
    req: TrainRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Start an AutoML training job. Returns job_id to poll for results."""
    if req.task_type not in ("classification", "regression", "clustering"):
        raise HTTPException(status_code=400, detail="task_type must be: classification | regression | clustering")

    dataset = db.query(Dataset).filter(
        Dataset.id == req.dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    job_id = str(uuid.uuid4())
    job = AutoMLJob(
        id=job_id,
        user_id=current_user["sub"],
        dataset_id=req.dataset_id,
        target_column=req.target_column,
        task_type=req.task_type,
        status="queued",
    )
    db.add(job)
    db.commit()

    background_tasks.add_task(
        _run_automl_training,
        job_id,
        dataset.file_path,
        dataset.file_type,
        req.target_column,
        req.task_type,
    )

    return {"job_id": job_id, "status": "queued", "message": "Training started — poll /jobs/{job_id} for results"}


@router.get("/jobs")
async def list_jobs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all AutoML jobs for the current user."""
    jobs = (
        db.query(AutoMLJob)
        .filter(AutoMLJob.user_id == current_user["sub"])
        .order_by(AutoMLJob.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": j.id,
            "dataset_id": j.dataset_id,
            "target_column": j.target_column,
            "task_type": j.task_type,
            "status": j.status,
            "best_model": j.best_model,
            "cv_score": j.cv_score,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full results for an AutoML job."""
    job = db.query(AutoMLJob).filter(
        AutoMLJob.id == job_id,
        AutoMLJob.user_id == current_user["sub"],
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": job.id,
        "dataset_id": job.dataset_id,
        "target_column": job.target_column,
        "task_type": job.task_type,
        "status": job.status,
        "best_model": job.best_model,
        "cv_score": job.cv_score,
        "metrics": job.metrics,
        "feature_importance": job.feature_importance,
        "confusion_matrix": job.confusion_matrix,
        "result_data": job.result_data,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/predict/{job_id}")
async def predict(
    job_id: str,
    req: PredictRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Run inference on a trained AutoML model."""
    job = db.query(AutoMLJob).filter(
        AutoMLJob.id == job_id,
        AutoMLJob.user_id == current_user["sub"],
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        raise HTTPException(status_code=400, detail=f"Model not ready — status: {job.status}")
    if not job.model_path:
        raise HTTPException(status_code=400, detail="Model file path not found")

    try:
        predictions = automl_service.predict(job.model_path, req.records)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Model file not found — it may have been deleted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")

    # Persist prediction record
    pred_record = AutoMLPrediction(
        id=str(uuid.uuid4()),
        job_id=job_id,
        user_id=current_user["sub"],
        input_data=req.records,
        predictions=predictions,
    )
    db.add(pred_record)
    db.commit()

    return {"job_id": job_id, "count": len(predictions), "predictions": predictions}


@router.delete("/models/{job_id}")
async def delete_model(
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a trained AutoML model and its job record."""
    import os

    job = db.query(AutoMLJob).filter(
        AutoMLJob.id == job_id,
        AutoMLJob.user_id == current_user["sub"],
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.model_path and os.path.exists(job.model_path):
        try:
            os.remove(job.model_path)
        except Exception as e:
            logger.warning(f"Could not delete model file: {e}")

    db.query(AutoMLPrediction).filter(AutoMLPrediction.job_id == job_id).delete()
    db.delete(job)
    db.commit()
    return {"message": "Model and job deleted successfully"}
