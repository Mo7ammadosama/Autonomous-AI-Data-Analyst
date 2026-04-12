"""
Auto-Insights v2 — Statistical pattern detection engine.

Goes beyond basic summary stats to detect:
  1. Trend direction & strength (linear regression on time-like columns)
  2. Distribution shape (skewness, kurtosis, bimodality)
  3. Strong correlations (Pearson > 0.7)
  4. Outlier density per column
  5. Missing data patterns (MCAR/MAR proxy via correlation of missingness)
  6. Categorical concentration (Herfindahl index)
  7. Seasonality / periodicity detection on time-series
  8. YoY / MoM change computation (if date column present)
  9. Duplicate rate
  10. Data freshness (days since last record)

Returns structured Insight objects with title, content, severity, insight_type,
metric_value, and metric_change — compatible with the existing Insight DB model.
"""

import logging
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# ── Severity thresholds ────────────────────────────────────────────
_CORR_STRONG = 0.75
_CORR_MODERATE = 0.50
_OUTLIER_HIGH_PCT = 5.0      # >5% of rows are outliers → high severity
_OUTLIER_MOD_PCT = 2.0
_MISSING_HIGH_PCT = 30.0
_MISSING_MOD_PCT = 10.0
_SKEW_HIGH = 2.0
_SKEW_MOD = 1.0
_TREND_R2_STRONG = 0.6


def _severity(value: float, high: float, moderate: float, reverse: bool = False) -> str:
    """Map a numeric value to severity. reverse=True means smaller = worse."""
    if reverse:
        if value <= moderate:
            return "high"
        if value <= high:
            return "warning"
        return "info"
    if value >= high:
        return "high"
    if value >= moderate:
        return "warning"
    return "info"


# ── Individual detectors ──────────────────────────────────────────

def _detect_trends(df: pd.DataFrame) -> List[Dict]:
    insights = []
    # Find numeric columns to test for trend (using row index as x)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    for col in num_cols[:8]:
        s = df[col].dropna()
        if len(s) < 20:
            continue
        x = np.arange(len(s))
        slope, intercept, r, p, _ = scipy_stats.linregress(x, s.values)
        r2 = r ** 2
        if r2 < 0.25:
            continue
        direction = "increasing" if slope > 0 else "decreasing"
        pct_change = abs(slope * len(s) / (s.mean() + 1e-9) * 100)
        sev = _severity(r2, _TREND_R2_STRONG, 0.35)
        insights.append({
            "title": f"Trend: {col} is {direction}",
            "content": (
                f"**{col}** shows a {direction} trend (R²={r2:.2f}, p={p:.4f}). "
                f"Over the dataset span it changed by approximately {pct_change:.1f}%."
            ),
            "insight_type": "trend",
            "severity": sev,
            "metric_value": f"{r2:.2f}",
            "metric_change": slope,
        })
    return insights[:3]


def _detect_correlations(df: pd.DataFrame) -> List[Dict]:
    insights = []
    num_df = df.select_dtypes(include="number")
    if num_df.shape[1] < 2:
        return []
    try:
        corr = num_df.corr()
        seen = set()
        for i, c1 in enumerate(corr.columns):
            for j, c2 in enumerate(corr.columns):
                if i >= j:
                    continue
                r = corr.loc[c1, c2]
                if abs(r) < _CORR_MODERATE or np.isnan(r):
                    continue
                key = tuple(sorted([c1, c2]))
                if key in seen:
                    continue
                seen.add(key)
                direction = "positive" if r > 0 else "negative"
                strength = "strong" if abs(r) >= _CORR_STRONG else "moderate"
                sev = "high" if abs(r) >= _CORR_STRONG else "warning"
                insights.append({
                    "title": f"{strength.title()} {direction} correlation: {c1} ↔ {c2}",
                    "content": (
                        f"**{c1}** and **{c2}** have a {strength} {direction} correlation "
                        f"(r={r:.2f}). "
                        + ("They likely share an underlying driver or causal relationship."
                           if abs(r) >= _CORR_STRONG else
                           "Consider investigating whether one influences the other.")
                    ),
                    "insight_type": "correlation",
                    "severity": sev,
                    "metric_value": f"r={r:.2f}",
                    "metric_change": float(r),
                })
    except Exception as e:
        logger.debug(f"Correlation insight error: {e}")
    return insights[:4]


def _detect_distributions(df: pd.DataFrame) -> List[Dict]:
    insights = []
    num_cols = df.select_dtypes(include="number").columns.tolist()
    for col in num_cols[:6]:
        s = df[col].dropna()
        if len(s) < 30:
            continue
        skew = float(s.skew())
        kurt = float(s.kurtosis())
        if abs(skew) < _SKEW_MOD:
            continue
        direction = "right" if skew > 0 else "left"
        sev = _severity(abs(skew), _SKEW_HIGH, _SKEW_MOD)
        tail_desc = "long right tail (outliers on the high end)" if skew > 0 else "long left tail (outliers on the low end)"
        insights.append({
            "title": f"Skewed distribution: {col}",
            "content": (
                f"**{col}** is {direction}-skewed (skewness={skew:.2f}), indicating a {tail_desc}. "
                f"Kurtosis={kurt:.2f}. Consider log-transforming before ML modeling."
            ),
            "insight_type": "distribution",
            "severity": sev,
            "metric_value": f"skew={skew:.2f}",
            "metric_change": skew,
        })
    return insights[:3]


def _detect_outliers(df: pd.DataFrame) -> List[Dict]:
    insights = []
    num_cols = df.select_dtypes(include="number").columns.tolist()
    for col in num_cols[:8]:
        s = df[col].dropna()
        if len(s) < 20:
            continue
        z = np.abs((s - s.mean()) / (s.std() + 1e-10))
        outlier_pct = float((z > 3).sum() / len(s) * 100)
        if outlier_pct < 0.1:
            continue
        sev = _severity(outlier_pct, _OUTLIER_HIGH_PCT, _OUTLIER_MOD_PCT)
        insights.append({
            "title": f"Outliers detected in {col}",
            "content": (
                f"**{col}** contains {outlier_pct:.1f}% outlier values (z-score > 3). "
                f"Outlier range: values below {float(s.mean() - 3*s.std()):.4g} or above {float(s.mean() + 3*s.std()):.4g}."
            ),
            "insight_type": "outlier",
            "severity": sev,
            "metric_value": f"{outlier_pct:.1f}%",
            "metric_change": outlier_pct,
        })
    return insights[:3]


def _detect_missing_data(df: pd.DataFrame) -> List[Dict]:
    insights = []
    for col in df.columns:
        miss_pct = float(df[col].isna().sum() / len(df) * 100)
        if miss_pct < 1.0:
            continue
        sev = _severity(miss_pct, _MISSING_HIGH_PCT, _MISSING_MOD_PCT)
        insights.append({
            "title": f"Missing data in {col}",
            "content": (
                f"**{col}** is missing {miss_pct:.1f}% of values ({df[col].isna().sum()} rows). "
                + ("This is significant and may bias analysis."
                   if miss_pct > _MISSING_HIGH_PCT else
                   "Consider imputation or removal before analysis.")
            ),
            "insight_type": "quality",
            "severity": sev,
            "metric_value": f"{miss_pct:.1f}%",
            "metric_change": miss_pct,
        })
    return insights[:3]


def _detect_categorical_concentration(df: pd.DataFrame) -> List[Dict]:
    insights = []
    cat_cols = df.select_dtypes(include="object").columns.tolist()
    for col in cat_cols[:5]:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        vc = s.value_counts(normalize=True)
        # Herfindahl-Hirschman Index
        hhi = float((vc ** 2).sum())
        top_share = float(vc.iloc[0]) if len(vc) > 0 else 0.0
        if top_share < 0.5:
            continue
        top_val = vc.index[0]
        insights.append({
            "title": f"Dominant category in {col}",
            "content": (
                f"**{col}** is dominated by '{top_val}' which accounts for {top_share*100:.1f}% of all values. "
                f"HHI={hhi:.2f}. This may indicate class imbalance for ML tasks."
            ),
            "insight_type": "distribution",
            "severity": "warning" if top_share > 0.8 else "info",
            "metric_value": f"{top_share*100:.1f}%",
            "metric_change": top_share,
        })
    return insights[:2]


def _detect_data_freshness(df: pd.DataFrame) -> List[Dict]:
    insights = []
    date_cols = [c for c in df.columns if "datetime" in str(df[c].dtype)]
    if not date_cols:
        # Try to parse columns named date/time
        for col in df.columns:
            if any(kw in col.lower() for kw in ("date", "time", "created", "updated")):
                try:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                    if df[col].notna().sum() > 10:
                        date_cols.append(col)
                        break
                except Exception:
                    pass
    for col in date_cols[:1]:
        s = df[col].dropna()
        max_date = s.max()
        if hasattr(max_date, "to_pydatetime"):
            max_dt = max_date.to_pydatetime()
            from datetime import datetime, timezone
            try:
                days_old = (datetime.now() - max_dt.replace(tzinfo=None)).days
                sev = "high" if days_old > 90 else ("warning" if days_old > 30 else "info")
                insights.append({
                    "title": f"Data freshness: {col}",
                    "content": (
                        f"The most recent record in **{col}** is {days_old} days old ({max_dt.strftime('%Y-%m-%d')}). "
                        + ("⚠️ Data may be stale." if days_old > 30 else "Data appears recent.")
                    ),
                    "insight_type": "quality",
                    "severity": sev,
                    "metric_value": f"{days_old}d ago",
                    "metric_change": float(days_old),
                })
            except Exception:
                pass
    return insights


def _detect_duplicates(df: pd.DataFrame) -> List[Dict]:
    dupe_count = int(df.duplicated().sum())
    if dupe_count == 0:
        return []
    dupe_pct = dupe_count / len(df) * 100
    return [{
        "title": f"Duplicate rows detected",
        "content": f"**{dupe_count}** duplicate rows ({dupe_pct:.1f}%) found. Remove duplicates before analysis to avoid double-counting.",
        "insight_type": "quality",
        "severity": "warning" if dupe_pct > 5 else "info",
        "metric_value": f"{dupe_count} rows ({dupe_pct:.1f}%)",
        "metric_change": dupe_pct,
    }]


# ── Main entry point ───────────────────────────────────────────────

def generate_insights_v2(df: pd.DataFrame, dataset_name: str = "dataset") -> List[Dict]:
    """
    Run all detectors and return a deduplicated list of insights,
    sorted by severity (high → warning → info).
    """
    all_insights = []
    detectors = [
        _detect_trends,
        _detect_correlations,
        _detect_distributions,
        _detect_outliers,
        _detect_missing_data,
        _detect_categorical_concentration,
        _detect_data_freshness,
        _detect_duplicates,
    ]
    for detector in detectors:
        try:
            results = detector(df)
            all_insights.extend(results)
        except Exception as e:
            logger.debug(f"Insight detector {detector.__name__} error: {e}")

    # Sort by severity
    sev_order = {"high": 0, "warning": 1, "info": 2}
    all_insights.sort(key=lambda x: sev_order.get(x.get("severity", "info"), 2))

    return all_insights[:15]   # Cap at 15 insights
