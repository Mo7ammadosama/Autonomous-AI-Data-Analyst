"""
Data Storytelling Service
Converts raw analysis results into human-readable narratives.
Uses LLM when available, falls back to template-based generation.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def _format_number(val: float) -> str:
    if abs(val) >= 1_000_000:
        return f"{val/1_000_000:.1f}M"
    if abs(val) >= 1_000:
        return f"{val/1_000:.1f}K"
    return f"{val:.2f}"


def _generate_quality_narrative(profile: Dict[str, Any]) -> str:
    """Narrate data quality from a profile dict."""
    rows = profile.get("shape", {}).get("rows", 0)
    cols = profile.get("shape", {}).get("columns", 0)
    duplicates = profile.get("duplicates", 0)
    missing = profile.get("missing_summary", {})

    parts = [f"The dataset contains **{rows:,} rows** and **{cols} columns**."]

    if duplicates > 0:
        pct = duplicates / max(rows, 1) * 100
        parts.append(f"**{duplicates} duplicate rows** ({pct:.1f}%) were identified and should be reviewed.")
    else:
        parts.append("No duplicate rows were found — the data appears clean.")

    if missing:
        worst = max(missing.items(), key=lambda x: x[1]["pct"])
        parts.append(
            f"**{len(missing)} column(s)** have missing values. "
            f"The most affected is **{worst[0]}** ({worst[1]['pct']:.1f}% missing)."
        )
    else:
        parts.append("No missing values were detected across any column.")

    return " ".join(parts)


def _generate_eda_narrative(stats: Dict[str, Any], correlations: Optional[Dict] = None) -> str:
    """Narrate EDA findings."""
    parts = []

    numeric = stats.get("numeric", {})
    if numeric:
        cols = list(numeric.keys())
        sample_col = cols[0] if cols else None
        if sample_col and "mean" in numeric.get(sample_col, {}):
            mean_val = numeric[sample_col]["mean"]
            std_val = numeric[sample_col].get("std", 0)
            parts.append(
                f"**{sample_col}** has a mean of **{_format_number(mean_val)}** "
                f"with a standard deviation of {_format_number(std_val)}, "
                f"indicating {'high' if std_val > mean_val else 'moderate'} variability."
            )

    if correlations:
        strong_pairs = correlations.get("strong_pairs", [])
        if strong_pairs:
            top = strong_pairs[0]
            direction = "positively" if top["correlation"] > 0 else "negatively"
            parts.append(
                f"**{top['col1']}** and **{top['col2']}** are strongly {direction} correlated "
                f"(r = {top['correlation']:.2f}), suggesting a meaningful relationship."
            )

    if not parts:
        parts.append("The dataset has been profiled. Statistical distributions and relationships have been computed.")

    return " ".join(parts)


def _generate_insights_narrative(insights: List[Dict[str, Any]]) -> str:
    """Convert a list of insight dicts to a narrative paragraph."""
    if not insights:
        return "No significant patterns were automatically detected."

    high_severity = [i for i in insights if i.get("severity") in ("warning", "critical")]
    success = [i for i in insights if i.get("severity") == "success"]

    parts = []
    if high_severity:
        parts.append(
            f"**{len(high_severity)} concern(s)** were flagged: "
            + "; ".join(i["title"] for i in high_severity[:3]) + "."
        )
    if success:
        parts.append(
            f"**Top performer**: {success[0]['title']} — {success[0].get('content', '')}"
        )
    if not parts and insights:
        parts.append(f"Key finding: {insights[0]['title']} — {insights[0].get('content', '')}")

    return " ".join(parts)


def _generate_anomaly_narrative(anomalies: Dict[str, Any]) -> str:
    """Narrate anomaly detection results."""
    alerts = anomalies.get("summary_alerts", [])
    col_anomalies = anomalies.get("column_anomalies", {})
    ts_anomalies = anomalies.get("time_series_anomalies")

    if not col_anomalies and not ts_anomalies:
        return "No significant anomalies were detected in this dataset."

    parts = []
    if col_anomalies:
        worst = max(col_anomalies.items(), key=lambda x: x[1]["pct"])
        parts.append(
            f"**{len(col_anomalies)} column(s)** contain anomalous values. "
            f"The most affected column is **{worst[0]}** with "
            f"{worst[1]['count']} outliers ({worst[1]['pct']:.1f}% of data)."
        )

    if ts_anomalies and ts_anomalies.get("total_anomalies", 0) > 0:
        n = ts_anomalies["total_anomalies"]
        col = ts_anomalies["column"]
        parts.append(
            f"In the time series of **{col}**, "
            f"**{n} anomalous event(s)** were detected, including sudden spikes or drops."
        )

    return " ".join(parts)


def generate_full_story(
    dataset_name: str,
    profile: Optional[Dict] = None,
    stats: Optional[Dict] = None,
    correlations: Optional[Dict] = None,
    insights: Optional[List[Dict]] = None,
    anomalies: Optional[Dict] = None,
    llm_service=None,
) -> str:
    """
    Generate a complete data story from analysis results.
    Uses LLM when available, otherwise uses template-based generation.
    """
    # Template-based story (always works)
    sections = []

    # Introduction
    sections.append(f"## 📊 Data Story: {dataset_name}\n")

    # Data Quality
    if profile:
        sections.append("### Data Quality\n" + _generate_quality_narrative(profile))

    # EDA
    if stats:
        sections.append("### Key Statistics\n" + _generate_eda_narrative(stats, correlations))

    # Insights
    if insights:
        sections.append("### Business Insights\n" + _generate_insights_narrative(insights))

    # Anomalies
    if anomalies:
        sections.append("### Anomaly Detection\n" + _generate_anomaly_narrative(anomalies))

    # Conclusion
    sections.append(
        "### Next Steps\n"
        "Consider applying data cleaning, running correlation analysis, and building "
        "a dashboard to track your key metrics over time."
    )

    template_story = "\n\n".join(sections)

    # Optionally enhance with LLM
    if llm_service:
        try:
            summary_context = f"""
Dataset: {dataset_name}
Rows: {profile.get('shape', {}).get('rows', 'N/A') if profile else 'N/A'}
Columns: {profile.get('shape', {}).get('columns', 'N/A') if profile else 'N/A'}
Insights count: {len(insights) if insights else 0}
Anomalies detected: {anomalies.get('total_alerts', 0) if anomalies else 0}
"""
            llm_story = llm_service.complete(
                system=(
                    "You are a senior data analyst. Write a concise, professional 3-paragraph data story "
                    "from the given context. Use business language. Include: data quality summary, "
                    "key findings, and recommended actions. Use markdown formatting."
                ),
                user=f"Context:\n{summary_context}\n\nBase narrative:\n{template_story[:1000]}",
                max_tokens=600,
            )
            if llm_story and len(llm_story) > 100:
                return template_story + "\n\n---\n\n### 🤖 AI Narrative\n" + llm_story
        except Exception as e:
            logger.warning(f"LLM story generation failed: {e}")

    return template_story


def generate_chart_explanation(chart: Dict[str, Any], llm_service=None) -> str:
    """
    Generate a natural-language explanation for a chart.
    """
    chart_type = chart.get("type", "chart")
    title = chart.get("title", "Untitled")
    data = chart.get("data", {})

    # Extract basic stats from chart data
    y_vals = data.get("y", []) if isinstance(data, dict) else []
    if isinstance(data, list) and data:
        y_vals = data[0].get("y", [])

    explanation = f"This **{chart_type} chart** titled '{title}'"

    if y_vals and isinstance(y_vals, list) and len(y_vals) > 0:
        numeric_y = [v for v in y_vals if isinstance(v, (int, float))]
        if numeric_y:
            explanation += (
                f" shows values ranging from {_format_number(min(numeric_y))} "
                f"to {_format_number(max(numeric_y))}, "
                f"with an average of {_format_number(sum(numeric_y)/len(numeric_y))}."
            )
    else:
        explanation += " visualizes the selected data dimensions."

    if llm_service:
        try:
            enhanced = llm_service.complete(
                system="You are a data visualization expert. Explain this chart in 1-2 sentences for a business audience.",
                user=f"Chart: {title}, Type: {chart_type}, Data summary: {str(data)[:300]}",
                max_tokens=150,
            )
            if enhanced and len(enhanced) > 20:
                return enhanced
        except Exception:
            pass

    return explanation
