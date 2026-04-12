"""
Automatic Data Analysis Pipeline
Runs a full analysis suite when a dataset is uploaded.
Results are stored in PipelineResult table.
"""

import logging
import time
from typing import Optional
from sqlalchemy.orm import Session

from models.database import PipelineResult, Dataset
from services.data_processor import (
    load_dataset, profile_dataset, compute_correlations,
    compute_descriptive_stats, detect_outliers,
)
from services.visualization import generate_auto_charts, generate_correlation_heatmap
from services.anomaly_detector import detect_anomalies
from services.storytelling import generate_full_story
from services.recommendation import generate_recommendations

logger = logging.getLogger(__name__)


def run_pipeline(dataset_id: str, db: Session, llm_service=None) -> Optional[PipelineResult]:
    """
    Execute the full automatic analysis pipeline for a dataset.
    Creates or updates a PipelineResult record.
    Safe to call in background — catches all exceptions.
    """
    # Fetch dataset record
    dataset: Optional[Dataset] = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset or dataset.status != "ready":
        logger.warning(f"Pipeline skipped for dataset {dataset_id}: not ready")
        return None

    # Upsert PipelineResult record
    result = db.query(PipelineResult).filter(PipelineResult.dataset_id == dataset_id).first()
    if not result:
        result = PipelineResult(dataset_id=dataset_id, status="running")
        db.add(result)
    else:
        result.status = "running"
    db.commit()

    start = time.time()
    try:
        # --- Load data ---
        df = load_dataset(dataset.file_path, dataset.file_type)

        # --- Profile ---
        profile = profile_dataset(df)

        # --- Stats & Correlations ---
        stats = compute_descriptive_stats(df)
        correlations = compute_correlations(df)

        # --- Outliers ---
        outliers = detect_outliers(df)

        # --- Anomaly Detection ---
        anomalies = detect_anomalies(df)

        # --- Charts (up to 6) ---
        charts = generate_auto_charts(df, max_charts=6)
        heatmap = generate_correlation_heatmap(df)
        if heatmap:
            charts.append(heatmap)

        # --- Insights (structured list) ---
        from services.ai_agent import AIDataAnalystAgent
        agent = AIDataAnalystAgent()
        insights = agent.generate_insights(df, dataset.name)

        # --- Recommendations ---
        recommendations = generate_recommendations(
            df,
            profile=profile,
            correlations=correlations,
            outliers=outliers,
            llm_service=llm_service,
        )

        # --- Story ---
        story = generate_full_story(
            dataset_name=dataset.name,
            profile=profile,
            stats=stats,
            correlations=correlations,
            insights=insights,
            anomalies=anomalies,
            llm_service=llm_service,
        )

        # --- EDA summary for storage ---
        eda = {
            "stats": stats,
            "correlations": correlations,
            "outliers": outliers,
        }

        # Update result
        result.profile = profile
        result.eda = eda
        result.insights = insights
        result.recommendations = recommendations
        result.story = story
        result.anomalies = anomalies
        result.charts = charts
        result.status = "done"
        db.commit()

        elapsed = round(time.time() - start, 2)
        logger.info(f"Pipeline completed for dataset {dataset_id} in {elapsed}s")
        return result

    except Exception as e:
        logger.error(f"Pipeline error for dataset {dataset_id}: {e}", exc_info=True)
        result.status = "error"
        result.error_message = str(e)
        db.commit()
        return result


def get_pipeline_result(dataset_id: str, db: Session) -> Optional[dict]:
    """Retrieve pipeline result as a serializable dict."""
    result = db.query(PipelineResult).filter(PipelineResult.dataset_id == dataset_id).first()
    if not result:
        return None
    return {
        "dataset_id": result.dataset_id,
        "status": result.status,
        "error_message": result.error_message,
        "profile": result.profile,
        "eda": result.eda,
        "insights": result.insights,
        "recommendations": result.recommendations,
        "story": result.story,
        "anomalies": result.anomalies,
        "charts": result.charts,
        "created_at": result.created_at.isoformat() if result.created_at else None,
        "updated_at": result.updated_at.isoformat() if result.updated_at else None,
    }
