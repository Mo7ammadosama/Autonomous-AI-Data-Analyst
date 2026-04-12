"""
Anomaly Detection Service
Detects statistical anomalies, sudden spikes/drops, and multi-variate outliers.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _zscore_anomalies(series: pd.Series, threshold: float = 3.0) -> List[int]:
    """Return indices where Z-score exceeds threshold."""
    mean = series.mean()
    std = series.std()
    if std == 0:
        return []
    z = (series - mean) / std
    return series[np.abs(z) > threshold].index.tolist()


def _iqr_anomalies(series: pd.Series, multiplier: float = 2.0) -> List[int]:
    """Return indices outside multiplier * IQR fence."""
    Q1 = series.quantile(0.25)
    Q3 = series.quantile(0.75)
    IQR = Q3 - Q1
    lower = Q1 - multiplier * IQR
    upper = Q3 + multiplier * IQR
    mask = (series < lower) | (series > upper)
    return series[mask].index.tolist()


def _change_point_anomalies(series: pd.Series, window: int = 7, threshold_pct: float = 30.0) -> List[Dict[str, Any]]:
    """
    Detect sudden pct-change spikes/drops using a rolling baseline.
    Returns a list of {index, value, pct_change, direction}.
    """
    if len(series) < window * 2:
        return []
    rolling_mean = series.rolling(window=window, min_periods=1).mean().shift(1)
    pct_change = ((series - rolling_mean) / rolling_mean.abs() * 100).replace([np.inf, -np.inf], np.nan).dropna()
    events = []
    for idx in pct_change[np.abs(pct_change) >= threshold_pct].index:
        events.append({
            "index": int(idx),
            "value": float(series.loc[idx]),
            "pct_change": round(float(pct_change.loc[idx]), 2),
            "direction": "spike" if pct_change.loc[idx] > 0 else "drop",
        })
    return events


def _time_series_anomalies(df: pd.DataFrame, date_col: str, value_col: str) -> Dict[str, Any]:
    """Full time-series anomaly analysis on a sorted date+value pair."""
    ts = df.sort_values(date_col)[[date_col, value_col]].dropna()
    series = ts[value_col].astype(float).reset_index(drop=True)
    dates = ts[date_col].reset_index(drop=True)

    zscore_idx = _zscore_anomalies(series)
    change_events = _change_point_anomalies(series)

    anomaly_points = []
    for idx in zscore_idx:
        anomaly_points.append({
            "date": str(dates.iloc[idx]) if idx < len(dates) else str(idx),
            "value": float(series.iloc[idx]),
            "type": "statistical_outlier",
            "description": f"Value {series.iloc[idx]:.2f} is statistically unusual (Z-score > 3σ)",
        })
    for evt in change_events:
        i = evt["index"]
        anomaly_points.append({
            "date": str(dates.iloc[i]) if i < len(dates) else str(i),
            "value": evt["value"],
            "type": evt["direction"],
            "pct_change": evt["pct_change"],
            "description": (
                f"{'Sudden spike' if evt['direction'] == 'spike' else 'Sudden drop'}: "
                f"{abs(evt['pct_change']):.1f}% change from baseline"
            ),
        })

    # Deduplicate by date
    seen = set()
    unique_points = []
    for p in anomaly_points:
        k = (p["date"], p["type"])
        if k not in seen:
            seen.add(k)
            unique_points.append(p)

    # Build alert messages
    alerts = []
    for p in unique_points[:5]:
        if p["type"] == "drop":
            alerts.append(f"⚠️ {value_col} dropped {abs(p.get('pct_change', 0)):.1f}% on {p['date']}")
        elif p["type"] == "spike":
            alerts.append(f"📈 {value_col} spiked {p.get('pct_change', 0):.1f}% on {p['date']}")
        else:
            alerts.append(f"🔍 Anomalous value ({p['value']:.2f}) on {p['date']}")

    return {
        "column": value_col,
        "date_column": date_col,
        "total_anomalies": len(unique_points),
        "anomaly_points": unique_points[:20],
        "alerts": alerts,
    }


def _isolation_forest_anomalies(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Multi-variate anomaly detection using Isolation Forest."""
    try:
        from sklearn.ensemble import IsolationForest
        numeric_df = df.select_dtypes(include=[np.number]).dropna()
        if numeric_df.shape[1] < 2 or len(numeric_df) < 20:
            return None
        clf = IsolationForest(contamination=0.05, random_state=42)
        labels = clf.fit_predict(numeric_df)
        anomaly_mask = labels == -1
        count = int(anomaly_mask.sum())
        return {
            "type": "multivariate",
            "total_anomalies": count,
            "anomaly_rate": round(count / len(numeric_df) * 100, 2),
            "description": (
                f"Isolation Forest detected {count} multi-variate anomalies "
                f"({count / len(numeric_df) * 100:.1f}% of rows) across {numeric_df.shape[1]} numeric columns."
            ),
        }
    except Exception as e:
        logger.warning(f"Isolation Forest failed: {e}")
        return None


def detect_anomalies(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Comprehensive anomaly detection:
    1. Per-column statistical outliers (Z-score + IQR)
    2. Time-series change-point detection (if date column present)
    3. Multi-variate anomaly detection (Isolation Forest)
    """
    results: Dict[str, Any] = {
        "column_anomalies": {},
        "time_series_anomalies": None,
        "multivariate_anomalies": None,
        "summary_alerts": [],
    }

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # --- Per-column anomalies ---
    for col in numeric_cols[:10]:
        series = df[col].dropna()
        if len(series) < 5:
            continue
        z_idx = _zscore_anomalies(series)
        iqr_idx = _iqr_anomalies(series)
        combined = list(set(z_idx) | set(iqr_idx))
        if combined:
            results["column_anomalies"][col] = {
                "count": len(combined),
                "pct": round(len(combined) / len(series) * 100, 2),
                "zscore_count": len(z_idx),
                "iqr_count": len(iqr_idx),
                "sample_values": [round(float(df[col].loc[i]), 4) for i in combined[:5] if i in df[col].index],
            }
            results["summary_alerts"].append(
                f"⚠️ {col}: {len(combined)} anomalous values detected ({len(combined)/len(series)*100:.1f}%)"
            )

    # --- Time-series anomalies ---
    date_col = None
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_col = col
            break
    if date_col is None:
        for col in df.select_dtypes(include="object").columns:
            try:
                parsed = pd.to_datetime(df[col], infer_datetime_format=True)
                df = df.copy()
                df[col] = parsed
                date_col = col
                break
            except Exception:
                continue

    if date_col and numeric_cols:
        target_col = numeric_cols[0]
        try:
            ts_result = _time_series_anomalies(df, date_col, target_col)
            results["time_series_anomalies"] = ts_result
            results["summary_alerts"].extend(ts_result.get("alerts", []))
        except Exception as e:
            logger.warning(f"Time series anomaly detection failed: {e}")

    # --- Multi-variate anomalies ---
    mv_result = _isolation_forest_anomalies(df)
    if mv_result:
        results["multivariate_anomalies"] = mv_result
        if mv_result["anomaly_rate"] > 5:
            results["summary_alerts"].append(mv_result["description"])

    results["total_alerts"] = len(results["summary_alerts"])
    return results
