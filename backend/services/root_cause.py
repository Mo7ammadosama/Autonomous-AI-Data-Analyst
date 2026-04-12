"""
Root Cause Analysis Service — explains WHY a metric changed.

Algorithm:
  1. Detect the change magnitude (z-score on rolling window or period comparison)
  2. Rank all other numeric columns by Pearson correlation with the target
  3. Segment by categorical columns to isolate which segment drove the change
  4. Use Claude (best narrative model) to generate a human-readable causal explanation
  5. Build a Plotly waterfall chart showing each factor's contribution
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RootCauseAnalyzer:
    """Analyzes why a metric changed over a given comparison period."""

    def __init__(self):
        from services.llm_router import llm_router
        self._router = llm_router

    # ── Public entry point ───────────────────────────────────────

    def analyze(
        self,
        df: pd.DataFrame,
        metric_column: str,
        date_column: Optional[str],
        comparison_period: str = "month",  # week | month | quarter
    ) -> Dict[str, Any]:
        """Run full RCA and return structured result + narrative + Plotly chart."""

        if metric_column not in df.columns:
            raise ValueError(f"Column '{metric_column}' not found in dataset")

        if not pd.api.types.is_numeric_dtype(df[metric_column]):
            raise ValueError(
                f"Column '{metric_column}' is text/categorical. "
                "Please select a numeric column for Root Cause Analysis."
            )

        # ── 1. Compute period-over-period change ─────────────────
        change_info = self._compute_change(df, metric_column, date_column, comparison_period)
        change_pct = change_info.get("change_pct", 0.0)

        # ── 2. Identify correlated drivers ───────────────────────
        top_drivers = self._find_drivers(df, metric_column)

        # ── 3. Segment analysis ──────────────────────────────────
        segments = self._segment_analysis(df, metric_column, date_column, comparison_period)

        # ── 4. LLM narrative ─────────────────────────────────────
        narrative = self._generate_narrative(
            metric_column, change_pct, comparison_period, top_drivers, segments
        )

        # ── 5. Waterfall chart ───────────────────────────────────
        chart = self._build_waterfall_chart(metric_column, change_pct, top_drivers, segments)

        # ── Confidence score ─────────────────────────────────────
        confidence = self._compute_confidence(top_drivers, segments, change_pct)

        return {
            "metric": metric_column,
            "change_pct": round(change_pct, 2),
            "period": comparison_period,
            "top_drivers": top_drivers[:5],
            "segments": segments[:5],
            "narrative": narrative,
            "chart": chart,
            "confidence": round(confidence, 2),
        }

    # ── Period change computation ────────────────────────────────

    def _compute_change(
        self,
        df: pd.DataFrame,
        metric_col: str,
        date_col: Optional[str],
        period: str,
    ) -> Dict[str, Any]:
        series = df[metric_col].dropna()
        if series.empty:
            return {"change_pct": 0.0}

        if date_col and date_col in df.columns:
            try:
                df2 = df.copy()
                df2[date_col] = pd.to_datetime(df2[date_col], errors="coerce")
                df2 = df2.dropna(subset=[date_col]).sort_values(date_col)

                cutoffs = {"week": 7, "month": 30, "quarter": 90}
                days = cutoffs.get(period, 30)
                max_date = df2[date_col].max()
                split = max_date - pd.Timedelta(days=days)

                recent = df2[df2[date_col] > split][metric_col].mean()
                prior = df2[df2[date_col] <= split][metric_col].mean()

                if prior and prior != 0:
                    change_pct = ((recent - prior) / abs(prior)) * 100
                else:
                    change_pct = 0.0
                return {"change_pct": change_pct, "recent_avg": recent, "prior_avg": prior}
            except Exception as e:
                logger.debug(f"Date-based change failed: {e}")

        # Fallback: compare first half vs second half
        mid = len(series) // 2
        if mid == 0:
            return {"change_pct": 0.0}
        prior = series.iloc[:mid].mean()
        recent = series.iloc[mid:].mean()
        change_pct = ((recent - prior) / abs(prior)) * 100 if prior != 0 else 0.0
        return {"change_pct": change_pct}

    # ── Driver correlation ───────────────────────────────────────

    def _find_drivers(self, df: pd.DataFrame, metric_col: str) -> List[Dict]:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        numeric_cols = [c for c in numeric_cols if c != metric_col]

        drivers = []
        target = df[metric_col].dropna()

        for col in numeric_cols[:30]:  # limit to 30 columns for performance
            try:
                other = df[col].dropna()
                aligned = pd.concat([target, other], axis=1).dropna()
                if len(aligned) < 5:
                    continue
                corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
                if not np.isnan(corr):
                    drivers.append({
                        "column": col,
                        "correlation": round(float(corr), 3),
                        "abs_correlation": round(abs(float(corr)), 3),
                        "direction": "positive" if corr > 0 else "negative",
                        "strength": "strong" if abs(corr) > 0.7 else "moderate" if abs(corr) > 0.4 else "weak",
                    })
            except Exception:
                continue

        return sorted(drivers, key=lambda x: x["abs_correlation"], reverse=True)

    # ── Segment analysis ─────────────────────────────────────────

    def _segment_analysis(
        self,
        df: pd.DataFrame,
        metric_col: str,
        date_col: Optional[str],
        period: str,
    ) -> List[Dict]:
        categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        segments = []

        cutoffs = {"week": 7, "month": 30, "quarter": 90}
        days = cutoffs.get(period, 30)

        for cat_col in categorical_cols[:5]:  # check top 5 categoricals
            try:
                if date_col and date_col in df.columns:
                    df2 = df.copy()
                    df2[date_col] = pd.to_datetime(df2[date_col], errors="coerce")
                    df2 = df2.dropna(subset=[date_col])
                    max_date = df2[date_col].max()
                    split = max_date - pd.Timedelta(days=days)
                    recent = df2[df2[date_col] > split]
                    prior = df2[df2[date_col] <= split]
                else:
                    mid = len(df) // 2
                    prior = df.iloc[:mid]
                    recent = df.iloc[mid:]

                for seg_val in df[cat_col].dropna().unique()[:8]:
                    r_vals = recent[recent[cat_col] == seg_val][metric_col].dropna()
                    p_vals = prior[prior[cat_col] == seg_val][metric_col].dropna()
                    if len(r_vals) < 2 or len(p_vals) < 2:
                        continue
                    r_mean = r_vals.mean()
                    p_mean = p_vals.mean()
                    if p_mean != 0:
                        seg_change = ((r_mean - p_mean) / abs(p_mean)) * 100
                        segments.append({
                            "dimension": cat_col,
                            "value": str(seg_val),
                            "change_pct": round(seg_change, 2),
                            "recent_avg": round(r_mean, 4),
                            "prior_avg": round(p_mean, 4),
                            "sample_size": len(r_vals) + len(p_vals),
                        })
            except Exception as e:
                logger.debug(f"Segment analysis failed for {cat_col}: {e}")

        return sorted(segments, key=lambda x: abs(x.get("change_pct", 0)), reverse=True)

    # ── LLM narrative ────────────────────────────────────────────

    def _generate_narrative(
        self,
        metric: str,
        change_pct: float,
        period: str,
        drivers: List[Dict],
        segments: List[Dict],
    ) -> str:
        direction = "increased" if change_pct > 0 else "decreased"
        top_driver_text = (
            ", ".join([f"{d['column']} ({d['direction']} correlation: {d['correlation']})" for d in drivers[:3]])
            if drivers else "no strong correlating variables found"
        )
        top_segment_text = (
            ", ".join([f"{s['dimension']}={s['value']} ({s['change_pct']:+.1f}%)" for s in segments[:3]])
            if segments else "no significant segment variations detected"
        )

        system = (
            "You are a senior data analyst providing root cause analysis. "
            "Be concise (3-5 sentences), actionable, and professional. "
            "Explain the likely causes, which segments were affected, and what to investigate next. "
            "Use markdown formatting with **bold** for key findings."
        )
        user = (
            f"The metric '{metric}' has {direction} by {abs(change_pct):.1f}% over the past {period}.\n\n"
            f"Top correlated variables: {top_driver_text}\n"
            f"Most affected segments: {top_segment_text}\n\n"
            "Provide a concise root cause analysis explanation."
        )

        try:
            return self._router.complete(system, user, max_tokens=400, task_type="root_cause")
        except Exception as e:
            logger.error(f"RCA narrative generation failed: {e}")
            return (
                f"**{metric}** has {direction} by **{abs(change_pct):.1f}%** over the past {period}. "
                f"The most correlated factors are: {top_driver_text}. "
                f"Segment analysis identified: {top_segment_text}."
            )

    # ── Plotly waterfall chart ───────────────────────────────────

    def _build_waterfall_chart(
        self,
        metric: str,
        change_pct: float,
        drivers: List[Dict],
        segments: List[Dict],
    ) -> Dict:
        labels = []
        values = []
        measures = []
        colors = []

        # Start with baseline
        labels.append("Baseline")
        values.append(0)
        measures.append("absolute")
        colors.append("#94a3b8")

        # Top correlated drivers as contributing factors
        for d in drivers[:4]:
            contribution = d["correlation"] * change_pct * 0.25  # weighted contribution
            labels.append(d["column"][:20])
            values.append(round(contribution, 2))
            measures.append("relative")
            colors.append("#22c55e" if contribution > 0 else "#ef4444")

        # Total
        labels.append(f"Total Change ({change_pct:+.1f}%)")
        values.append(round(change_pct, 2))
        measures.append("total")
        colors.append("#3b82f6" if change_pct > 0 else "#ef4444")

        return {
            "data": [{
                "type": "waterfall",
                "x": labels,
                "y": values,
                "measure": measures,
                "connector": {"line": {"color": "#64748b"}},
                "increasing": {"marker": {"color": "#22c55e"}},
                "decreasing": {"marker": {"color": "#ef4444"}},
                "totals": {"marker": {"color": "#3b82f6"}},
                "text": [f"{v:+.1f}%" for v in values],
                "textposition": "outside",
            }],
            "layout": {
                "title": f"Root Cause Analysis: {metric}",
                "xaxis": {"title": "Factor"},
                "yaxis": {"title": "Change Contribution (%)"},
                "plot_bgcolor": "#0f172a",
                "paper_bgcolor": "#0f172a",
                "font": {"color": "#e2e8f0"},
                "showlegend": False,
                "height": 400,
            },
        }

    # ── Confidence score ─────────────────────────────────────────

    def _compute_confidence(
        self,
        drivers: List[Dict],
        segments: List[Dict],
        change_pct: float,
    ) -> float:
        score = 0.5  # base

        # Strong correlations boost confidence
        if drivers:
            max_corr = drivers[0]["abs_correlation"]
            score += max_corr * 0.25

        # Clear segment differentiation boosts confidence
        if segments:
            max_seg_change = max(abs(s.get("change_pct", 0)) for s in segments)
            if max_seg_change > 20:
                score += 0.15
            elif max_seg_change > 10:
                score += 0.08

        # Large change is more reliable signal
        if abs(change_pct) > 20:
            score += 0.1

        return min(score, 0.95)


# ── Singleton ─────────────────────────────────────────────────────
rca_analyzer = RootCauseAnalyzer()
