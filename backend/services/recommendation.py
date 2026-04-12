"""
Business Recommendation Engine
Generates actionable recommendations from analysis results.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _correlation_recommendations(correlations: Optional[Dict]) -> List[Dict[str, Any]]:
    """Generate recommendations from strong correlations."""
    recs = []
    if not correlations:
        return recs
    for pair in correlations.get("strong_pairs", [])[:3]:
        c1, c2, r = pair["col1"], pair["col2"], pair["correlation"]
        if r > 0.8:
            recs.append({
                "type": "correlation",
                "priority": "high",
                "title": f"Leverage {c1} → {c2} relationship",
                "description": (
                    f"Strong positive correlation (r={r:.2f}) between {c1} and {c2}. "
                    f"Increasing {c1} is likely to drive {c2} upward."
                ),
                "action": f"Monitor {c1} as a leading indicator for {c2}.",
                "expected_impact": "Predictive power for planning and forecasting.",
            })
        elif r < -0.8:
            recs.append({
                "type": "correlation",
                "priority": "medium",
                "title": f"Trade-off detected: {c1} vs {c2}",
                "description": (
                    f"Strong negative correlation (r={r:.2f}) between {c1} and {c2}. "
                    f"Optimizing one may reduce the other."
                ),
                "action": f"Find the optimal balance between {c1} and {c2}.",
                "expected_impact": "Better resource allocation.",
            })
    return recs


def _outlier_recommendations(outliers: Optional[Dict]) -> List[Dict[str, Any]]:
    """Generate recommendations from detected outliers."""
    recs = []
    if not outliers:
        return recs
    high_pct_cols = [(col, info) for col, info in outliers.items() if info["pct"] > 5]
    for col, info in high_pct_cols[:2]:
        recs.append({
            "type": "data_quality",
            "priority": "high",
            "title": f"Investigate outliers in {col}",
            "description": (
                f"{info['count']} outliers ({info['pct']:.1f}%) detected in {col}. "
                f"Normal range: [{info['lower_bound']:.2f}, {info['upper_bound']:.2f}]."
            ),
            "action": f"Audit records in {col} outside the normal range. Apply data cleaning or investigate root cause.",
            "expected_impact": "Improved data quality and model accuracy.",
        })
    return recs


def _missing_data_recommendations(profile: Optional[Dict]) -> List[Dict[str, Any]]:
    """Generate recommendations from missing data patterns."""
    recs = []
    if not profile:
        return recs
    missing = profile.get("missing_summary", {})
    critical = [(col, info) for col, info in missing.items() if info["pct"] > 20]
    if critical:
        cols_str = ", ".join(col for col, _ in critical[:3])
        recs.append({
            "type": "data_quality",
            "priority": "high",
            "title": "Address critical missing data",
            "description": (
                f"Columns {cols_str} have >20% missing values, "
                "which may significantly bias analysis results."
            ),
            "action": (
                "Use imputation (median/mode fill) or collect additional data. "
                "Consider dropping columns with >50% missing."
            ),
            "expected_impact": "Substantially more reliable analysis and predictions.",
        })
    return recs


def _segment_recommendations(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Generate segment-level performance recommendations."""
    recs = []
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not cat_cols or not num_cols:
        return recs

    cat_col = cat_cols[0]
    num_col = num_cols[0]

    try:
        grouped = df.groupby(cat_col)[num_col].mean().sort_values(ascending=False)
        if len(grouped) < 2:
            return recs

        top_segment = grouped.index[0]
        bottom_segment = grouped.index[-1]
        top_val = float(grouped.iloc[0])
        bottom_val = float(grouped.iloc[-1])
        gap_pct = (top_val - bottom_val) / abs(bottom_val) * 100 if bottom_val != 0 else 0

        recs.append({
            "type": "segment",
            "priority": "medium",
            "title": f"Grow {bottom_segment} segment",
            "description": (
                f"**{top_segment}** leads with avg {num_col} of {top_val:.2f}, "
                f"while **{bottom_segment}** lags at {bottom_val:.2f} ({gap_pct:.0f}% gap)."
            ),
            "action": (
                f"Analyze what drives {top_segment}'s performance and apply similar strategies to {bottom_segment}. "
                f"Closing half the gap could increase overall {num_col} by ~{gap_pct/4:.0f}%."
            ),
            "expected_impact": f"Potential {gap_pct/4:.0f}% improvement in avg {num_col}.",
        })
    except Exception as e:
        logger.warning(f"Segment recommendation failed: {e}")

    return recs


def _trend_recommendations(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect trends and generate forward-looking recommendations."""
    recs = []
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    for col in num_cols[:2]:
        series = df[col].dropna()
        if len(series) < 10:
            continue
        # Split into halves and compare means
        half = len(series) // 2
        first_half_mean = float(series.iloc[:half].mean())
        second_half_mean = float(series.iloc[half:].mean())
        if first_half_mean == 0:
            continue
        change_pct = (second_half_mean - first_half_mean) / abs(first_half_mean) * 100
        if abs(change_pct) > 10:
            direction = "increasing" if change_pct > 0 else "declining"
            priority = "high" if abs(change_pct) > 25 else "medium"
            recs.append({
                "type": "trend",
                "priority": priority,
                "title": f"{col} is {direction} ({change_pct:+.1f}%)",
                "description": (
                    f"{col} shows a {direction} trend: avg moved from "
                    f"{first_half_mean:.2f} to {second_half_mean:.2f} ({change_pct:+.1f}%)."
                ),
                "action": (
                    f"{'Capitalize on the growth — scale investment in drivers of ' + col + '.' if change_pct > 0 else 'Investigate root causes of decline in ' + col + ' and implement corrective actions.'}"
                ),
                "expected_impact": f"{'Sustain or accelerate growth' if change_pct > 0 else 'Prevent further decline and recover performance'}.",
            })
    return recs


def generate_recommendations(
    df: pd.DataFrame,
    profile: Optional[Dict] = None,
    correlations: Optional[Dict] = None,
    outliers: Optional[Dict] = None,
    llm_service=None,
) -> List[Dict[str, Any]]:
    """
    Main entry point: generate prioritized business recommendations.
    Returns a list of recommendation dicts sorted by priority.
    """
    all_recs: List[Dict[str, Any]] = []

    all_recs.extend(_missing_data_recommendations(profile))
    all_recs.extend(_outlier_recommendations(outliers))
    all_recs.extend(_correlation_recommendations(correlations))
    all_recs.extend(_segment_recommendations(df))
    all_recs.extend(_trend_recommendations(df))

    # Sort: high > medium > low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    all_recs.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 2))

    # Optionally enhance top recommendation with LLM
    if llm_service and all_recs:
        try:
            top = all_recs[0]
            enhanced_action = llm_service.complete(
                system=(
                    "You are a senior business analyst. Provide one specific, quantified, "
                    "actionable recommendation based on the finding. Keep it to 2 sentences."
                ),
                user=f"Finding: {top['title']}\nDescription: {top['description']}",
                max_tokens=150,
            )
            if enhanced_action and len(enhanced_action) > 20:
                all_recs[0]["ai_action"] = enhanced_action
        except Exception as e:
            logger.warning(f"LLM recommendation enhancement failed: {e}")

    return all_recs[:8]  # Return top 8 recommendations
