"""
Autonomous Data Analyst Pipeline
Orchestrates a complete end-to-end analysis:
  profile → quality → correlations → trends → anomalies
  → forecasting → insights → recommendations → story
  → auto dashboard → PDF report
"""

import logging
import time
import uuid
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from models.database import Dataset, PipelineResult, Dashboard

logger = logging.getLogger(__name__)


# ── Progress stages ────────────────────────────────────────────────────────────
STAGES = [
    "profiling",
    "statistics",
    "correlations",
    "anomaly_detection",
    "forecasting",
    "insights",
    "recommendations",
    "storytelling",
    "dashboard",
    "complete",
]


def run_autonomous_analysis(
    dataset_id: str,
    db: Session,
    owner_id: str,
    llm_service=None,
) -> Dict[str, Any]:
    """
    Execute the full autonomous analysis suite.
    Returns a rich result dict with every analysis layer.
    """
    dataset: Optional[Dataset] = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == owner_id,
    ).first()

    if not dataset:
        return {"error": "Dataset not found or access denied."}

    if dataset.status != "ready":
        return {"error": f"Dataset is not ready (status={dataset.status})."}

    start = time.time()
    result: Dict[str, Any] = {
        "dataset_id": dataset_id,
        "dataset_name": dataset.name,
        "stages_completed": [],
        "profile": None,
        "stats": None,
        "correlations": None,
        "outliers": None,
        "anomalies": None,
        "forecast": None,
        "insights": [],
        "recommendations": [],
        "story": "",
        "charts": [],
        "dashboard_id": None,
        "pipeline_status": "running",
        "elapsed_seconds": 0,
        "errors": [],
    }

    # ── helpers ────────────────────────────────────────────────────────────────
    def _stage(name: str):
        result["stages_completed"].append(name)
        logger.info(f"[Autonomous] stage={name} | dataset={dataset_id}")

    def _err(stage: str, exc: Exception):
        msg = f"{stage}: {str(exc)}"
        result["errors"].append(msg)
        logger.warning(f"[Autonomous] non-fatal error — {msg}")

    # ── Load data ──────────────────────────────────────────────────────────────
    try:
        from services.data_processor import (
            load_dataset, profile_dataset, compute_descriptive_stats,
            compute_correlations, detect_outliers, detect_dataset_type,
        )
        import numpy as np
        df = load_dataset(dataset.file_path, dataset.file_type)
    except Exception as e:
        result["pipeline_status"] = "error"
        result["errors"].append(f"load: {e}")
        return result

    # Detect dataset type (time-series vs cross-sectional) once, used in stages 3 & 5
    try:
        ds_type = detect_dataset_type(df)
        result["dataset_type"] = ds_type["type"]
        result["dataset_type_reason"] = ds_type.get("reason", "")
    except Exception as e:
        ds_type = {"type": "UNKNOWN"}
        _err("detect_dataset_type", e)

    # Pre-compute filtered numeric df for correlation (exclude rank/year/id)
    _CORR_SKIP = {"year", "yr", "id", "rank", "no", "number", "index", "sno"}
    _numeric_df = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all")
    _clean_cols = [c for c in _numeric_df.columns
                   if c.lower().strip() not in _CORR_SKIP and not c.lower().startswith("rank")]
    _corr_df = _numeric_df[_clean_cols] if len(_clean_cols) >= 2 else _numeric_df

    # ── Stage 1: Profiling ─────────────────────────────────────────────────────
    try:
        result["profile"] = profile_dataset(df)
        _stage("profiling")
    except Exception as e:
        _err("profiling", e)

    # ── Stage 2: Statistics ────────────────────────────────────────────────────
    try:
        result["stats"] = compute_descriptive_stats(df)
        _stage("statistics")
    except Exception as e:
        _err("statistics", e)

    # ── Stage 3: Correlations (filtered numeric cols — excludes rank/year/id) ──
    try:
        result["correlations"] = compute_correlations(_corr_df)
        _stage("correlations")
    except Exception as e:
        _err("correlations", e)

    # ── Stage 4: Outliers + Anomaly Detection ──────────────────────────────────
    try:
        result["outliers"] = detect_outliers(df)
        from services.anomaly_detector import detect_anomalies
        result["anomalies"] = detect_anomalies(df)
        _stage("anomaly_detection")
    except Exception as e:
        _err("anomaly_detection", e)

    # ── Stage 5: Forecasting (time-series only, skipped for cross-sectional) ──
    if ds_type["type"] == "CROSS_SECTIONAL":
        result["forecast"] = None
        reason = ds_type.get("reason", "cross-sectional dataset")
        result["errors"].append(f"forecasting: skipped — {reason}")
        logger.info(f"[Autonomous] Forecasting skipped: {reason}")
        # Still mark stage as complete (it was evaluated, not errored)
        _stage("forecasting")
    else:
        try:
            from services.forecasting import run_forecast
            fc = run_forecast(df, periods=30, method="auto")
            if "error" not in fc:
                result["forecast"] = {
                    "target_column": fc.get("target_column"),
                    "method": fc.get("method"),
                    "periods": fc.get("periods"),
                    "summary": fc.get("summary"),
                    "metrics": fc.get("metrics"),
                    "chart": fc.get("chart"),
                }
                _stage("forecasting")
            else:
                result["errors"].append(f"forecasting: {fc['error']}")
        except Exception as e:
            _err("forecasting", e)

    # ── Stage 6: Insights ──────────────────────────────────────────────────────
    try:
        from services.ai_agent import AIDataAnalystAgent
        agent = AIDataAnalystAgent()
        result["insights"] = agent.generate_insights(df, dataset.name)
        _stage("insights")
    except Exception as e:
        _err("insights", e)

    # ── Stage 7: Recommendations ───────────────────────────────────────────────
    try:
        from services.recommendation import generate_recommendations
        result["recommendations"] = generate_recommendations(
            df,
            profile=result["profile"] or {},
            correlations=result["correlations"],
            outliers=result["outliers"],
            llm_service=llm_service,
        )
        _stage("recommendations")
    except Exception as e:
        _err("recommendations", e)

    # ── Stage 8: Story ─────────────────────────────────────────────────────────
    try:
        from services.storytelling import generate_full_story
        result["story"] = generate_full_story(
            dataset_name=dataset.name,
            profile=result["profile"] or {},
            stats=result["stats"] or {},
            correlations=result["correlations"],
            insights=result["insights"],
            anomalies=result["anomalies"],
            llm_service=llm_service,
        )
        _stage("storytelling")
    except Exception as e:
        _err("storytelling", e)

    # ── Stage 9: Auto Charts + Dashboard ──────────────────────────────────────
    try:
        from services.visualization import generate_auto_charts, generate_correlation_heatmap
        charts = generate_auto_charts(df, max_charts=6)
        # Use filtered numeric df for heatmap (excludes rank/year/id)
        hm = generate_correlation_heatmap(_corr_df)
        if hm:
            charts.append(hm)
        result["charts"] = charts

        # Persist auto-dashboard
        dash = Dashboard(
            id=str(uuid.uuid4()),
            title=f"Auto Dashboard — {dataset.name}",
            description=f"Autonomous analysis dashboard generated for {dataset.name}",
            user_id=owner_id,
            dataset_id=dataset_id,
            charts=charts,
        )
        db.add(dash)
        db.commit()
        result["dashboard_id"] = dash.id
        _stage("dashboard")
    except Exception as e:
        _err("dashboard", e)

    # ── Persist to PipelineResult so existing pipeline page benefits ───────────
    try:
        pr = db.query(PipelineResult).filter(PipelineResult.dataset_id == dataset_id).first()
        if not pr:
            pr = PipelineResult(dataset_id=dataset_id)
            db.add(pr)
        pr.status = "done"
        pr.profile = result["profile"]
        pr.eda = {"stats": result["stats"], "correlations": result["correlations"], "outliers": result["outliers"]}
        pr.insights = result["insights"]
        pr.recommendations = result["recommendations"]
        pr.story = result["story"]
        pr.anomalies = result["anomalies"]
        pr.charts = result["charts"]
        db.commit()
    except Exception as e:
        _err("pipeline_persist", e)

    elapsed = round(time.time() - start, 2)
    result["elapsed_seconds"] = elapsed
    result["pipeline_status"] = "complete"
    _stage("complete")

    logger.info(f"[Autonomous] Completed in {elapsed}s | stages={result['stages_completed']}")
    return result
