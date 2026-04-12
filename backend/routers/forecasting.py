"""
Forecasting Router
GET  /api/forecasting/{dataset_id}/auto       — auto-detect date + target
POST /api/forecasting/{dataset_id}/forecast   — specify columns + periods
GET  /api/forecasting/{dataset_id}/columns    — list forecastable column pairs
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import logging

from models.database import get_db, Dataset, ForecastResult
from services.data_processor import load_dataset
from services.forecasting import run_forecast, _detect_date_and_target
from security.auth import get_current_user
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)


class ForecastRequest(BaseModel):
    date_column: Optional[str] = None
    target_column: Optional[str] = None
    periods: int = 30
    method: str = "auto"  # auto | arima | exp_smoothing | linear


def _get_dataset_or_404(dataset_id: str, current_user: dict, db: Session) -> Dataset:
    ds = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"]
    ).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.get("/{dataset_id}/columns")
async def get_forecastable_columns(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return detected date columns, numeric target columns, and whether dataset is a time series."""
    ds = _get_dataset_or_404(dataset_id, current_user, db)
    try:
        import pandas as pd
        import numpy as np
        from services.data_processor import detect_dataset_type

        df = load_dataset(ds.file_path, ds.file_type)

        # Detect dataset type first
        ds_type = detect_dataset_type(df)
        is_time_series = ds_type["type"] == "TIME_SERIES"

        date_cols = []
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                date_cols.append(col)
            elif df[col].dtype == object:
                try:
                    pd.to_datetime(df[col].head(5), infer_datetime_format=True)
                    date_cols.append(col)
                except Exception:
                    pass

        # For integer year columns: only include as date if multiple unique values
        _YEAR_NAMES = {"year", "yr", "año"}
        for col in df.columns:
            if col.lower().strip() in _YEAR_NAMES and col not in date_cols:
                if df[col].nunique() > 1:
                    date_cols.append(col)

        # Exclude year/rank/id from numeric targets
        _SKIP = {"year", "yr", "id", "rank", "no", "number", "index"}
        all_numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        numeric_cols = [c for c in all_numeric if c.lower().strip() not in _SKIP]
        if not numeric_cols:
            numeric_cols = all_numeric  # fallback

        auto_date, auto_target = _detect_date_and_target(df)

        not_time_series_reason = ds_type.get("reason") if not is_time_series else None

        return {
            "date_columns": date_cols,
            "numeric_columns": numeric_cols,
            "auto_detected": {"date_column": auto_date, "target_column": auto_target},
            "is_time_series": is_time_series,
            "not_time_series_reason": not_time_series_reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}/auto")
async def auto_forecast(
    dataset_id: str,
    periods: int = 30,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Auto-detect columns and run forecast."""
    ds = _get_dataset_or_404(dataset_id, current_user, db)
    try:
        df = load_dataset(ds.file_path, ds.file_type)
        result = run_forecast(df, periods=periods, method="auto")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        _save_forecast(dataset_id, result, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{dataset_id}/forecast")
async def run_custom_forecast(
    dataset_id: str,
    req: ForecastRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run forecast with user-specified columns and parameters."""
    ds = _get_dataset_or_404(dataset_id, current_user, db)
    try:
        df = load_dataset(ds.file_path, ds.file_type)
        result = run_forecast(
            df,
            date_column=req.date_column,
            target_column=req.target_column,
            periods=req.periods,
            method=req.method,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        _save_forecast(dataset_id, result, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _save_forecast(dataset_id: str, result: dict, db: Session):
    """Persist forecast result to DB."""
    try:
        record = ForecastResult(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            date_column=result.get("date_column", ""),
            target_column=result.get("target_column", ""),
            periods=result.get("periods", 30),
            method=result.get("method", "auto"),
            forecast_data=result.get("forecast"),
            metrics=result.get("metrics"),
            chart=result.get("chart"),
        )
        db.add(record)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to save forecast result: {e}")
