"""
Analytics router — with Redis response caching for expensive endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import logging

from models.database import get_db, Dataset, AnalysisResult
from services.data_processor import load_dataset, compute_correlations, compute_descriptive_stats, detect_outliers, profile_dataset
from services.visualization import generate_auto_charts, generate_correlation_heatmap, generate_box_plots
from services.cache_service import cache
from security.auth import get_current_user
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

CACHE_TTL_OVERVIEW = 600      # 10 min
CACHE_TTL_CORRELATIONS = 1800 # 30 min
CACHE_TTL_CHARTS = 1800


@router.get("/{dataset_id}/overview")
async def get_overview(dataset_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    cache_key = f"analytics:{dataset_id}:overview"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        profile = profile_dataset(df)
        stats = compute_descriptive_stats(df)
        charts = generate_auto_charts(df, max_charts=6)
        result = {"profile": profile, "stats": stats, "charts": charts}
        cache.set(cache_key, result, CACHE_TTL_OVERVIEW)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/correlations")
async def get_correlations(dataset_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    cache_key = f"analytics:{dataset_id}:correlations"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        import numpy as np
        df = load_dataset(dataset.file_path, dataset.file_type)

        # Only use meaningful numeric columns — exclude rank/year/id
        _SKIP = {"year", "yr", "id", "rank", "no", "number", "index", "sno"}
        numeric_df = df.select_dtypes(include=[np.number]).dropna(axis=1, how="all")
        clean_cols = [c for c in numeric_df.columns
                      if c.lower().strip() not in _SKIP and not c.lower().startswith("rank")]
        if len(clean_cols) >= 2:
            numeric_df = numeric_df[clean_cols]

        if numeric_df.shape[1] < 2:
            return {"correlations": None, "chart": None,
                    "message": "Need at least 2 numeric columns for correlation analysis."}

        corr_data = compute_correlations(numeric_df)
        chart = generate_correlation_heatmap(numeric_df)
        result = {"correlations": corr_data, "chart": chart}
        cache.set(cache_key, result, CACHE_TTL_CORRELATIONS)
        return result
    except Exception as e:
        logger.warning(f"Correlation endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/outliers")
async def get_outliers(dataset_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        outliers = detect_outliers(df)
        charts = generate_box_plots(df)
        return {"outliers": outliers, "charts": charts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/charts")
async def get_charts(dataset_id: str, max_charts: int = 8, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        charts = generate_auto_charts(df, max_charts=max_charts)
        return {"charts": charts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MLRequest(BaseModel):
    analysis_type: str  # clustering, regression, classification
    target_column: Optional[str] = None
    n_clusters: Optional[int] = 3


@router.post("/{dataset_id}/ml")
async def run_ml_analysis(dataset_id: str, req: MLRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        import pandas as pd
        import numpy as np
        from sklearn.preprocessing import StandardScaler
        from sklearn.cluster import KMeans
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import r2_score, silhouette_score

        df = load_dataset(dataset.file_path, dataset.file_type)
        numeric_df = df.select_dtypes(include=[np.number]).dropna()

        if req.analysis_type == "clustering":
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(numeric_df)
            n = min(req.n_clusters or 3, len(numeric_df) - 1, 10)
            kmeans = KMeans(n_clusters=n, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X_scaled)
            sil_score = float(silhouette_score(X_scaled, labels)) if n > 1 else 0.0

            cluster_summary = {}
            numeric_df["_cluster"] = labels
            for c in range(n):
                cluster_data = numeric_df[numeric_df["_cluster"] == c].drop("_cluster", axis=1)
                cluster_summary[f"Cluster {c}"] = {
                    "size": int(len(cluster_data)),
                    "means": {col: round(float(cluster_data[col].mean()), 3) for col in cluster_data.columns[:5]},
                }

            return {
                "type": "clustering",
                "n_clusters": n,
                "silhouette_score": round(sil_score, 4),
                "cluster_summary": cluster_summary,
                "labels": labels.tolist()[:100],
            }

        elif req.analysis_type == "regression" and req.target_column:
            if req.target_column not in df.columns:
                raise HTTPException(status_code=400, detail="Target column not found")
            feature_cols = [c for c in numeric_df.columns if c != req.target_column][:10]
            X = numeric_df[feature_cols]
            y = numeric_df[req.target_column]
            if len(X) < 10:
                raise HTTPException(status_code=400, detail="Not enough data for regression")
            model = LinearRegression()
            model.fit(X, y)
            y_pred = model.predict(X)
            r2 = float(r2_score(y, y_pred))
            coefficients = {col: round(float(coef), 4) for col, coef in zip(feature_cols, model.coef_)}
            return {
                "type": "regression",
                "target": req.target_column,
                "r2_score": round(r2, 4),
                "intercept": round(float(model.intercept_), 4),
                "coefficients": coefficients,
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid analysis type or missing parameters")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Natural Language Query endpoint
# ──────────────────────────────────────────────

class NLQueryRequest(BaseModel):
    question: str


@router.post("/{dataset_id}/nl-query")
async def natural_language_query(
    dataset_id: str,
    req: NLQueryRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Natural language → analysis → chart + explanation pipeline.
    Example: "Show revenue by region" or "Top 10 products by profit"
    """
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        from services.ai_agent import AIDataAnalystAgent
        df = load_dataset(dataset.file_path, dataset.file_type)
        agent = AIDataAnalystAgent()
        result = agent.analyze_question(req.question, df, dataset.name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Anomaly detection endpoint
# ──────────────────────────────────────────────

@router.get("/{dataset_id}/anomalies-full")
async def get_full_anomalies(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Full anomaly detection: statistical, time-series, and multivariate."""
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        from services.anomaly_detector import detect_anomalies
        df = load_dataset(dataset.file_path, dataset.file_type)
        return detect_anomalies(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
