"""
What-If Scenario Engine — Qlik AutoML What-If style.

Given a trained AutoML model and user-defined input assumptions (slider overrides),
simulates a prediction and compares it to the baseline.

Returns: predicted value, delta vs baseline, per-feature impact, and Plotly chart.
"""

import logging
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  Core Simulation
# ═══════════════════════════════════════════════════════════════

def _load_model(model_path: str):
    """Load a pickled sklearn model."""
    if not model_path or not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    with open(model_path, "rb") as f:
        return pickle.load(f)


def _make_baseline(result_data: Optional[List[Dict]], feature_names: List[str]) -> Dict[str, float]:
    """Compute feature means from stored training sample data as baseline."""
    if not result_data:
        return {f: 0.0 for f in feature_names}
    baseline = {}
    for feat in feature_names:
        vals = [row[feat] for row in result_data if feat in row and isinstance(row[feat], (int, float))]
        baseline[feat] = float(np.mean(vals)) if vals else 0.0
    return baseline


def run_scenario(
    model,
    feature_names: List[str],
    baseline_inputs: Dict[str, float],
    overrides: Dict[str, float],
    task_type: str = "regression",
) -> Dict[str, Any]:
    """
    Run baseline + scenario prediction and return comparison.

    Args:
        model: sklearn model / pipeline
        feature_names: list of input feature names
        baseline_inputs: {feature: value} for baseline (dataset means)
        overrides: {feature: value} the user wants to change
        task_type: regression | classification

    Returns:
        {baseline_prediction, scenario_prediction, delta, delta_pct, feature_impacts, ...}
    """
    # Build baseline and scenario arrays
    baseline_row = [baseline_inputs.get(f, 0.0) for f in feature_names]
    scenario_row = [overrides.get(f, baseline_inputs.get(f, 0.0)) for f in feature_names]

    X_base = np.array([baseline_row])
    X_scen = np.array([scenario_row])

    # Predict
    if task_type == "regression":
        base_pred = float(model.predict(X_base)[0])
        scen_pred = float(model.predict(X_scen)[0])
    elif task_type == "classification":
        if hasattr(model, "predict_proba"):
            base_pred = float(model.predict_proba(X_base)[0].max())
            scen_pred = float(model.predict_proba(X_scen)[0].max())
        else:
            base_pred = float(model.predict(X_base)[0])
            scen_pred = float(model.predict(X_scen)[0])
    else:
        base_pred = 0.0
        scen_pred = 0.0

    delta = scen_pred - base_pred
    delta_pct = (delta / abs(base_pred) * 100) if abs(base_pred) > 1e-9 else 0.0

    # Per-feature impact (linear approximation via one-at-a-time sensitivity)
    feature_impacts = []
    for feat in overrides:
        if feat not in feature_names:
            continue
        idx = feature_names.index(feat)
        row_single = baseline_row.copy()
        row_single[idx] = overrides[feat]
        if task_type == "regression":
            single_pred = float(model.predict(np.array([row_single]))[0])
        else:
            single_pred = float(model.predict_proba(np.array([row_single]))[0].max()) if hasattr(model, "predict_proba") else 0.0
        impact = single_pred - base_pred
        feature_impacts.append({
            "feature": feat,
            "baseline_value": baseline_inputs.get(feat, 0.0),
            "scenario_value": overrides[feat],
            "prediction_impact": round(impact, 6),
            "direction": "positive" if impact > 0 else "negative",
        })
    feature_impacts.sort(key=lambda x: abs(x["prediction_impact"]), reverse=True)

    # Build waterfall Plotly chart
    chart = _build_waterfall_chart(base_pred, feature_impacts, scen_pred)

    return {
        "baseline_prediction": round(base_pred, 6),
        "scenario_prediction": round(scen_pred, 6),
        "delta": round(delta, 6),
        "delta_pct": round(delta_pct, 2),
        "feature_impacts": feature_impacts,
        "chart": chart,
    }


def _build_waterfall_chart(
    baseline: float,
    feature_impacts: List[Dict],
    final: float,
) -> Dict[str, Any]:
    """Build a Plotly waterfall chart showing how each feature change contributes."""
    import plotly.graph_objects as go

    names = ["Baseline"] + [f["feature"] for f in feature_impacts] + ["Scenario Total"]
    values = [baseline] + [f["prediction_impact"] for f in feature_impacts] + [0]
    measures = ["absolute"] + ["relative"] * len(feature_impacts) + ["total"]

    colors = (
        ["#6366f1"]
        + ["#22c55e" if f["prediction_impact"] > 0 else "#ef4444" for f in feature_impacts]
        + ["#8b5cf6"]
    )

    fig = go.Figure(go.Waterfall(
        name="What-If",
        orientation="v",
        measure=measures,
        x=names,
        y=values,
        connector={"line": {"color": "rgba(255,255,255,0.2)"}},
        increasing={"marker": {"color": "#22c55e"}},
        decreasing={"marker": {"color": "#ef4444"}},
        totals={"marker": {"color": "#8b5cf6"}},
        text=[f"{v:+.3f}" if i > 0 else f"{v:.3f}" for i, v in enumerate(values)],
        textposition="outside",
    ))
    fig.update_layout(
        title="What-If Impact Analysis",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.03)",
        font={"color": "#e5e7eb"},
        height=400,
        showlegend=False,
    )
    return fig.to_dict()


# ═══════════════════════════════════════════════════════════════
#  Scenario Service — used by the router
# ═══════════════════════════════════════════════════════════════

def simulate_scenario(
    automl_job,            # AutoMLJob ORM object
    input_assumptions: Dict[str, float],
) -> Dict[str, Any]:
    """
    High-level function called by the router.
    Loads model from job.model_path, computes baseline from job.result_data.
    """
    if not automl_job.model_path:
        raise ValueError("AutoML job has no saved model. Train the model first.")
    if automl_job.status != "done":
        raise ValueError(f"AutoML job is not done (status: {automl_job.status})")

    model = _load_model(automl_job.model_path)

    feature_importance = automl_job.feature_importance or {}
    feature_names = list(feature_importance.keys()) if feature_importance else []
    if not feature_names:
        raise ValueError("No feature names found in AutoML job.")

    baseline = _make_baseline(automl_job.result_data, feature_names)

    return run_scenario(
        model=model,
        feature_names=feature_names,
        baseline_inputs=baseline,
        overrides=input_assumptions,
        task_type=automl_job.task_type,
    )
