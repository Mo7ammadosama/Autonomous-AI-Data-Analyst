"""
Visualization service using Plotly-compatible chart specs
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

CHART_COLORS = ["#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#14b8a6"]


def generate_auto_charts(df: pd.DataFrame, max_charts: int = 6) -> List[Dict[str, Any]]:
    """Auto-generate appropriate charts based on data types"""
    charts = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

    # Sample for performance
    sample_df = df.sample(min(1000, len(df)), random_state=42) if len(df) > 1000 else df

    # 1. Distribution histograms for numeric
    for col in numeric_cols[:2]:
        charts.append({
            "id": f"hist_{col}",
            "type": "histogram",
            "title": f"Distribution: {col}",
            "data": [{"x": sample_df[col].dropna().tolist(), "type": "histogram", "name": col, "marker": {"color": CHART_COLORS[0]}}],
            "layout": {
                "title": f"Distribution of {col}",
                "xaxis": {"title": col},
                "yaxis": {"title": "Count"},
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#94a3b8"},
            },
        })
        if len(charts) >= max_charts:
            return charts

    # 2. Bar charts for categorical × numeric
    if cat_cols and numeric_cols:
        cat_col = cat_cols[0]
        num_col = numeric_cols[0]
        try:
            grouped = df.groupby(cat_col)[num_col].mean().sort_values(ascending=False).head(12)
            charts.append({
                "id": f"bar_{cat_col}_{num_col}",
                "type": "bar",
                "title": f"{num_col} by {cat_col}",
                "data": [{
                    "x": grouped.index.tolist(),
                    "y": [round(v, 2) for v in grouped.values.tolist()],
                    "type": "bar",
                    "name": num_col,
                    "marker": {"color": CHART_COLORS[1]},
                }],
                "layout": {
                    "title": f"Average {num_col} by {cat_col}",
                    "xaxis": {"title": cat_col},
                    "yaxis": {"title": f"Avg {num_col}"},
                    "paper_bgcolor": "rgba(0,0,0,0)",
                    "plot_bgcolor": "rgba(0,0,0,0)",
                    "font": {"color": "#94a3b8"},
                },
            })
        except Exception as e:
            logger.warning(f"Bar chart error: {e}")

        if len(charts) >= max_charts:
            return charts

    # 3. Scatter plot for two numeric cols
    if len(numeric_cols) >= 2:
        x_col, y_col = numeric_cols[0], numeric_cols[1]
        charts.append({
            "id": f"scatter_{x_col}_{y_col}",
            "type": "scatter",
            "title": f"{x_col} vs {y_col}",
            "data": [{
                "x": sample_df[x_col].tolist(),
                "y": sample_df[y_col].tolist(),
                "type": "scatter",
                "mode": "markers",
                "name": f"{x_col} vs {y_col}",
                "marker": {"color": CHART_COLORS[2], "opacity": 0.6, "size": 6},
            }],
            "layout": {
                "title": f"{x_col} vs {y_col}",
                "xaxis": {"title": x_col},
                "yaxis": {"title": y_col},
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#94a3b8"},
            },
        })
        if len(charts) >= max_charts:
            return charts

    # 4. Time series line chart
    if date_cols and numeric_cols:
        date_col = date_cols[0]
        num_col = numeric_cols[0]
        try:
            ts = df.sort_values(date_col)[[date_col, num_col]].dropna()
            if len(ts) > 500:
                ts = ts.resample("D", on=date_col)[num_col].mean().reset_index()
            charts.append({
                "id": f"line_{num_col}",
                "type": "line",
                "title": f"{num_col} Over Time",
                "data": [{
                    "x": ts[date_col].astype(str).tolist()[:500],
                    "y": ts[num_col].tolist()[:500],
                    "type": "scatter",
                    "mode": "lines",
                    "name": num_col,
                    "line": {"color": CHART_COLORS[3], "width": 2},
                }],
                "layout": {
                    "title": f"{num_col} Over Time",
                    "xaxis": {"title": date_col},
                    "yaxis": {"title": num_col},
                    "paper_bgcolor": "rgba(0,0,0,0)",
                    "plot_bgcolor": "rgba(0,0,0,0)",
                    "font": {"color": "#94a3b8"},
                },
            })
        except Exception as e:
            logger.warning(f"Time series error: {e}")

        if len(charts) >= max_charts:
            return charts

    # 5. Pie chart for categorical
    if cat_cols:
        cat_col = cat_cols[0]
        vc = df[cat_col].value_counts().head(8)
        charts.append({
            "id": f"pie_{cat_col}",
            "type": "pie",
            "title": f"{cat_col} Distribution",
            "data": [{
                "labels": vc.index.tolist(),
                "values": vc.values.tolist(),
                "type": "pie",
                "hole": 0.4,
                "marker": {"colors": CHART_COLORS},
            }],
            "layout": {
                "title": f"{cat_col} Breakdown",
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#94a3b8"},
            },
        })

    return charts[:max_charts]


def generate_correlation_heatmap(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Generate correlation heatmap"""
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return None

    cols = numeric_df.columns.tolist()[:12]
    numeric_df = numeric_df[cols]
    corr = numeric_df.corr().round(3)

    z = corr.values.tolist()
    text = [[f"{v:.2f}" for v in row] for row in z]

    return {
        "id": "correlation_heatmap",
        "type": "heatmap",
        "title": "Correlation Matrix",
        "data": [{
            "z": z,
            "x": cols,
            "y": cols,
            "type": "heatmap",
            "colorscale": "RdBu",
            "text": text,
            "texttemplate": "%{text}",
            "zmin": -1,
            "zmax": 1,
        }],
        "layout": {
            "title": "Correlation Heatmap",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#94a3b8"},
        },
    }


def generate_box_plots(df: pd.DataFrame) -> List[Dict]:
    """Generate box plots for numeric columns"""
    charts = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()[:4]
    sample = df.sample(min(1000, len(df)), random_state=42) if len(df) > 1000 else df

    data_traces = []
    for i, col in enumerate(numeric_cols):
        data_traces.append({
            "y": sample[col].dropna().tolist(),
            "type": "box",
            "name": col,
            "marker": {"color": CHART_COLORS[i % len(CHART_COLORS)]},
        })

    if data_traces:
        charts.append({
            "id": "box_plots",
            "type": "box",
            "title": "Box Plots: Numeric Columns",
            "data": data_traces,
            "layout": {
                "title": "Distribution Box Plots",
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#94a3b8"},
            },
        })
    return charts
