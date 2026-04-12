"""
What-If Scenario Router — /api/scenarios/

Lets users drag sliders to adjust input features and see how a trained
AutoML model's prediction changes in real-time — Qlik AutoML style.
"""

import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, AutoMLJob, ScenarioResult
from security.auth import get_current_user

router = APIRouter(prefix="/api/scenarios", tags=["What-If Scenarios"])


# ─── Schemas ────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    automl_job_id: str
    name: Optional[str] = None
    input_assumptions: Dict[str, float]    # {feature_name: value}
    save: bool = False                     # persist the scenario


class ScenarioOut(BaseModel):
    id: str
    automl_job_id: str
    name: Optional[str]
    input_assumptions: Optional[dict]
    baseline_prediction: Optional[float]
    scenario_prediction: Optional[float]
    delta: Optional[float]
    delta_pct: Optional[float]
    feature_impacts: Optional[list]
    is_shared: bool
    share_token: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Endpoints ─────────────────────────────────────────────────

@router.post("/simulate")
def simulate_what_if(
    body: SimulateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run a what-if simulation against a trained AutoML model.
    Returns predicted outcome + per-feature impact breakdown + waterfall chart.
    """
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]

    job = db.query(AutoMLJob).filter(
        AutoMLJob.id == body.automl_job_id,
        AutoMLJob.user_id == uid,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="AutoML job not found")

    from services.scenario_engine import simulate_scenario
    try:
        result = simulate_scenario(job, body.input_assumptions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Optionally save
    saved_id = None
    if body.save:
        scenario = ScenarioResult(
            user_id=uid,
            automl_job_id=body.automl_job_id,
            name=body.name or f"Scenario {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            input_assumptions=body.input_assumptions,
            baseline_prediction=result["baseline_prediction"],
            scenario_prediction=result["scenario_prediction"],
            delta=result["delta"],
            delta_pct=result["delta_pct"],
            feature_impacts=result["feature_impacts"],
            chart=result.get("chart"),
        )
        db.add(scenario)
        db.commit()
        db.refresh(scenario)
        saved_id = scenario.id

    return {
        **result,
        "scenario_id": saved_id,
        "automl_job_id": body.automl_job_id,
        "input_assumptions": body.input_assumptions,
    }


@router.get("/")
def list_scenarios(
    automl_job_id: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List saved what-if scenarios."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    q = db.query(ScenarioResult).filter(ScenarioResult.user_id == uid)
    if automl_job_id:
        q = q.filter(ScenarioResult.automl_job_id == automl_job_id)
    scenarios = q.order_by(ScenarioResult.created_at.desc()).limit(50).all()
    return [_scenario_out(s) for s in scenarios]


@router.get("/{scenario_id}")
def get_scenario(
    scenario_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a saved scenario by ID."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    s = db.query(ScenarioResult).filter(
        ScenarioResult.id == scenario_id,
        ScenarioResult.user_id == uid,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _scenario_out(s)


@router.delete("/{scenario_id}")
def delete_scenario(
    scenario_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a saved scenario."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    s = db.query(ScenarioResult).filter(
        ScenarioResult.id == scenario_id,
        ScenarioResult.user_id == uid,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scenario not found")
    db.delete(s)
    db.commit()
    return {"status": "deleted"}


@router.post("/{scenario_id}/share")
def share_scenario(
    scenario_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a public share link for a scenario snapshot."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    s = db.query(ScenarioResult).filter(
        ScenarioResult.id == scenario_id,
        ScenarioResult.user_id == uid,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if not s.share_token:
        s.share_token = secrets.token_urlsafe(24)
        s.is_shared = True
        db.commit()
    return {"share_token": s.share_token, "share_url": f"/api/scenarios/public/{s.share_token}"}


@router.get("/public/{token}")
def get_public_scenario(
    token: str,
    db: Session = Depends(get_db),
):
    """Public view of a shared scenario (no auth required)."""
    s = db.query(ScenarioResult).filter(
        ScenarioResult.share_token == token,
        ScenarioResult.is_shared == True,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Shared scenario not found")
    return _scenario_out(s)


@router.get("/model-features/{automl_job_id}")
def get_model_features(
    automl_job_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get feature names + baseline ranges for slider UI construction.
    Returns min, max, mean for each feature from the training data.
    """
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    job = db.query(AutoMLJob).filter(
        AutoMLJob.id == automl_job_id,
        AutoMLJob.user_id == uid,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="AutoML job not found")
    if job.status != "done":
        raise HTTPException(status_code=400, detail="Model is not trained yet")

    feature_names = list((job.feature_importance or {}).keys())
    result_data = job.result_data or []

    features_meta = []
    import numpy as np
    for feat in feature_names:
        vals = [row[feat] for row in result_data if feat in row and isinstance(row[feat], (int, float))]
        if vals:
            features_meta.append({
                "name": feat,
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals)),
            })
        else:
            features_meta.append({"name": feat, "min": 0, "max": 100, "mean": 50, "std": 10})

    return {
        "automl_job_id": automl_job_id,
        "task_type": job.task_type,
        "target_column": job.target_column,
        "features": features_meta,
    }


def _scenario_out(s: ScenarioResult) -> Dict[str, Any]:
    return {
        "id": s.id,
        "automl_job_id": s.automl_job_id,
        "name": s.name,
        "input_assumptions": s.input_assumptions,
        "baseline_prediction": s.baseline_prediction,
        "scenario_prediction": s.scenario_prediction,
        "delta": s.delta,
        "delta_pct": s.delta_pct,
        "feature_impacts": s.feature_impacts,
        "chart": s.chart,
        "is_shared": s.is_shared,
        "share_token": s.share_token,
        "created_at": s.created_at,
    }
