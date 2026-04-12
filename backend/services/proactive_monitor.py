"""
Proactive Intelligence Monitor — Tableau Pulse style push analytics.

Scans user datasets automatically, detects anomalies / trend shifts /
record values, generates LLM narratives, and pushes insights to users
via WebSocket, Email, and Slack — before they even ask.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from models.database import (
    Dataset, ProactiveInsight, ProactiveConfig, User,
    Notification, SessionLocal,
)

logger = logging.getLogger(__name__)

# ── sensitivity thresholds ──────────────────────────────────────
SENSITIVITY_THRESHOLDS = {
    "low":    {"zscore": 4.0, "change_pct": 40.0},
    "medium": {"zscore": 3.0, "change_pct": 20.0},
    "high":   {"zscore": 2.0, "change_pct": 10.0},
}


# ═══════════════════════════════════════════════════════════════
#  Core Detection Functions
# ═══════════════════════════════════════════════════════════════

def _detect_anomalies(series: pd.Series, zscore_thresh: float) -> List[Dict[str, Any]]:
    """Z-score anomaly detection on a numeric series."""
    mean = series.mean()
    std = series.std()
    if std == 0 or len(series) < 5:
        return []
    z = (series - mean) / std
    anomaly_idx = series[np.abs(z) > zscore_thresh].index.tolist()
    results = []
    for idx in anomaly_idx[-3:]:  # last 3 only
        val = series.loc[idx]
        direction = "spike" if val > mean else "drop"
        results.append({
            "index": str(idx),
            "value": float(val),
            "zscore": float(abs(z.loc[idx])),
            "direction": direction,
            "mean": float(mean),
        })
    return results


def _detect_trend_shift(series: pd.Series, change_pct_thresh: float) -> Optional[Dict[str, Any]]:
    """Compare last window vs previous window to detect trend shifts."""
    if len(series) < 10:
        return None
    half = len(series) // 2
    prev_mean = series.iloc[:half].mean()
    curr_mean = series.iloc[half:].mean()
    if prev_mean == 0:
        return None
    change_pct = ((curr_mean - prev_mean) / abs(prev_mean)) * 100
    if abs(change_pct) >= change_pct_thresh:
        return {
            "previous_mean": float(prev_mean),
            "current_mean": float(curr_mean),
            "change_pct": float(round(change_pct, 2)),
            "direction": "up" if change_pct > 0 else "down",
        }
    return None


def _detect_record(series: pd.Series) -> Optional[Dict[str, Any]]:
    """Detect if the latest value is a new all-time high or low."""
    if len(series) < 5:
        return None
    latest = series.iloc[-1]
    historical = series.iloc[:-1]
    if latest > historical.max():
        return {"type": "record_high", "value": float(latest), "previous_max": float(historical.max())}
    if latest < historical.min():
        return {"type": "record_low", "value": float(latest), "previous_min": float(historical.min())}
    return None


def _compute_drivers(df: pd.DataFrame, metric_col: str) -> List[Dict[str, Any]]:
    """
    Find top categorical columns that explain variance in the metric.
    Returns top 3 dimension/value combos with their contribution %.
    """
    drivers = []
    cat_cols = [c for c in df.columns if c != metric_col and df[c].dtype == object][:5]
    total_mean = df[metric_col].mean()
    if total_mean == 0:
        return drivers
    for col in cat_cols:
        try:
            grouped = df.groupby(col)[metric_col].mean()
            for val, grp_mean in grouped.items():
                contribution = abs((grp_mean - total_mean) / total_mean) * 100
                if contribution > 5:
                    drivers.append({
                        "dimension": col,
                        "value": str(val),
                        "mean": float(round(grp_mean, 4)),
                        "contribution_pct": float(round(contribution, 1)),
                    })
        except Exception:
            continue
    drivers.sort(key=lambda x: x["contribution_pct"], reverse=True)
    return drivers[:3]


# ═══════════════════════════════════════════════════════════════
#  Narrative Generation
# ═══════════════════════════════════════════════════════════════

def _generate_narrative(
    insight_type: str,
    metric_name: str,
    dataset_name: str,
    change_pct: Optional[float],
    current_value: Optional[float],
    previous_value: Optional[float],
    drivers: List[Dict[str, Any]],
) -> str:
    """
    Generate a plain-English narrative without LLM (fast, always available).
    A separate async version uses the LLM for richer narratives.
    """
    direction = ""
    if change_pct is not None:
        direction = "increased" if change_pct > 0 else "decreased"
        pct_str = f"{abs(change_pct):.1f}%"
    else:
        pct_str = ""

    narrative_map = {
        "anomaly": (
            f"⚠️ Anomaly detected in **{metric_name}** ({dataset_name}): "
            f"current value {current_value:.2f} is significantly outside normal range."
        ),
        "trend_shift": (
            f"📈 **{metric_name}** ({dataset_name}) has {direction} by {pct_str}. "
            + (
                f"Primary driver: **{drivers[0]['dimension']}** = {drivers[0]['value']} "
                f"({drivers[0]['contribution_pct']:.0f}% contribution)."
                if drivers else ""
            )
        ),
        "record_high": (
            f"🏆 **{metric_name}** ({dataset_name}) has reached a new all-time high of {current_value:.2f}!"
        ),
        "record_low": (
            f"🔴 **{metric_name}** ({dataset_name}) has dropped to a new all-time low of {current_value:.2f}."
        ),
        "data_quality": (
            f"⚠️ Data quality issue detected in **{dataset_name}**: "
            f"column **{metric_name}** has significant missing values or outliers."
        ),
    }
    return narrative_map.get(insight_type, f"New insight detected for {metric_name} in {dataset_name}.")


async def _generate_narrative_llm(
    insight_type: str,
    metric_name: str,
    dataset_name: str,
    change_pct: Optional[float],
    current_value: Optional[float],
    drivers: List[Dict[str, Any]],
) -> str:
    """Use LLM to generate a richer narrative (with fallback to rule-based)."""
    try:
        from services.llm_service import call_llm
        drivers_text = ""
        if drivers:
            top = drivers[0]
            drivers_text = (
                f"The primary driver is {top['dimension']} = {top['value']} "
                f"({top['contribution_pct']:.0f}% of the change)."
            )
        direction = "increased" if (change_pct or 0) > 0 else "decreased"
        pct_str = f"{abs(change_pct):.1f}%" if change_pct else ""

        prompt = f"""You are a data analyst generating a concise insight notification.
Dataset: {dataset_name}
Metric: {metric_name}
Event: {insight_type}
Change: {direction} {pct_str}
{drivers_text}

Write a 1-2 sentence plain-English insight notification. Be specific and actionable. No fluff."""

        result = await call_llm(prompt, task_type="narrative", max_tokens=150)
        return result.strip() if result else _generate_narrative(
            insight_type, metric_name, dataset_name, change_pct, current_value, None, drivers
        )
    except Exception:
        return _generate_narrative(
            insight_type, metric_name, dataset_name, change_pct, current_value, None, drivers
        )


# ═══════════════════════════════════════════════════════════════
#  Dataset Scanner
# ═══════════════════════════════════════════════════════════════

def _scan_dataset(dataset: Dataset, sensitivity: str) -> List[Dict[str, Any]]:
    """
    Load dataset file and run all detection algorithms.
    Returns a list of raw insight dicts (not yet saved to DB).
    """
    thresholds = SENSITIVITY_THRESHOLDS.get(sensitivity, SENSITIVITY_THRESHOLDS["medium"])
    zscore_thresh = thresholds["zscore"]
    change_pct_thresh = thresholds["change_pct"]

    file_path = dataset.file_path
    if not file_path or not os.path.exists(file_path):
        return []

    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(file_path, nrows=10000)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, nrows=10000)
        elif ext == ".parquet":
            df = pd.read_parquet(file_path)
        elif ext == ".json":
            df = pd.read_json(file_path)
        else:
            return []
    except Exception as e:
        logger.warning(f"Could not load dataset {dataset.id}: {e}")
        return []

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()[:8]
    raw_insights = []

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 5:
            continue

        # 1. Anomaly detection
        anomalies = _detect_anomalies(series, zscore_thresh)
        if anomalies:
            latest = anomalies[-1]
            raw_insights.append({
                "insight_type": "anomaly",
                "metric_name": col,
                "current_value": latest["value"],
                "previous_value": latest["mean"],
                "change_pct": None,
                "drivers": _compute_drivers(df, col),
                "severity": "warning" if latest["zscore"] < 4 else "critical",
            })

        # 2. Trend shift detection
        trend = _detect_trend_shift(series, change_pct_thresh)
        if trend:
            raw_insights.append({
                "insight_type": "trend_shift",
                "metric_name": col,
                "current_value": trend["current_mean"],
                "previous_value": trend["previous_mean"],
                "change_pct": trend["change_pct"],
                "drivers": _compute_drivers(df, col),
                "severity": "warning" if abs(trend["change_pct"]) < 30 else "critical",
            })

        # 3. Record detection
        record = _detect_record(series)
        if record:
            raw_insights.append({
                "insight_type": record["type"],
                "metric_name": col,
                "current_value": record["value"],
                "previous_value": record.get("previous_max") or record.get("previous_min"),
                "change_pct": None,
                "drivers": [],
                "severity": "info",
            })

    return raw_insights


# ═══════════════════════════════════════════════════════════════
#  Notification Dispatch
# ═══════════════════════════════════════════════════════════════

async def _dispatch_insight(
    user: User,
    config: "ProactiveConfig",
    insight: ProactiveInsight,
    db: Session,
) -> List[str]:
    """Push insight to configured channels. Returns list of channels used."""
    sent_via = []

    # 1. In-app notification (always created)
    notif = Notification(
        user_id=user.id,
        type="proactive_insight",
        title=f"New Insight: {insight.metric_name}",
        message=insight.narrative[:200] if insight.narrative else "",
        link=f"/proactive",
    )
    db.add(notif)
    sent_via.append("in_app")

    # 2. WebSocket push
    if config.notify_websocket:
        try:
            from services.websocket_manager import manager
            # manager uses room-based broadcast; user's room is their user_id
            await manager.broadcast(user.id, {
                "type": "proactive_insight",
                "insight_id": insight.id,
                "metric_name": insight.metric_name,
                "insight_type": insight.insight_type,
                "narrative": insight.narrative,
                "severity": insight.severity,
                "change_pct": insight.change_pct,
            })
            sent_via.append("websocket")
        except Exception as e:
            logger.warning(f"WebSocket push failed for user {user.id}: {e}")

    # 3. Email
    if config.notify_email and user.email:
        try:
            from services.notification_channels import EmailChannel
            email_ch = EmailChannel()
            await email_ch.send(
                to=user.email,
                subject=f"DataMind Insight: {insight.metric_name} {insight.insight_type}",
                body=insight.narrative or "",
            )
            sent_via.append("email")
        except Exception as e:
            logger.warning(f"Email dispatch failed for user {user.id}: {e}")

    # 4. Slack
    if config.notify_slack and config.slack_webhook_url:
        try:
            from services.notification_channels import SlackChannel
            slack = SlackChannel()
            severity_emoji = {"info": "📊", "warning": "⚠️", "critical": "🚨"}.get(insight.severity, "📊")
            await slack.send(
                webhook_url=config.slack_webhook_url,
                title=f"{severity_emoji} DataMind Insight",
                message=insight.narrative or "",
            )
            sent_via.append("slack")
        except Exception as e:
            logger.warning(f"Slack dispatch failed for user {user.id}: {e}")

    return sent_via


# ═══════════════════════════════════════════════════════════════
#  Main Scanner — called by Celery task
# ═══════════════════════════════════════════════════════════════

async def run_proactive_scan(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point called by Celery beat task.
    Scans datasets for all active users (or a specific user) and stores insights.

    Returns summary stats for logging.
    """
    db: Session = SessionLocal()
    stats = {"users_scanned": 0, "insights_generated": 0, "errors": 0}

    try:
        # Fetch active configs
        query = db.query(ProactiveConfig).filter(ProactiveConfig.is_enabled == True)
        if user_id:
            query = query.filter(ProactiveConfig.user_id == user_id)
        configs = query.all()

        for config in configs:
            try:
                user = db.query(User).filter(User.id == config.user_id).first()
                if not user or not user.is_active:
                    continue

                # Determine which datasets to scan
                if config.monitored_datasets:
                    datasets = (
                        db.query(Dataset)
                        .filter(
                            Dataset.id.in_(config.monitored_datasets),
                            Dataset.status == "ready",
                        )
                        .all()
                    )
                else:
                    datasets = (
                        db.query(Dataset)
                        .filter(
                            Dataset.owner_id == user.id,
                            Dataset.status == "ready",
                        )
                        .limit(10)
                        .all()
                    )

                for dataset in datasets:
                    raw_insights = _scan_dataset(dataset, config.anomaly_sensitivity)

                    for raw in raw_insights:
                        # Avoid duplicate insights within last 24h for same metric+type
                        cutoff = datetime.utcnow() - timedelta(hours=24)
                        existing = (
                            db.query(ProactiveInsight)
                            .filter(
                                ProactiveInsight.user_id == user.id,
                                ProactiveInsight.dataset_id == dataset.id,
                                ProactiveInsight.metric_name == raw["metric_name"],
                                ProactiveInsight.insight_type == raw["insight_type"],
                                ProactiveInsight.created_at >= cutoff,
                            )
                            .first()
                        )
                        if existing:
                            continue

                        # Generate narrative (rule-based fast path)
                        narrative = _generate_narrative(
                            insight_type=raw["insight_type"],
                            metric_name=raw["metric_name"],
                            dataset_name=dataset.name,
                            change_pct=raw.get("change_pct"),
                            current_value=raw.get("current_value"),
                            previous_value=raw.get("previous_value"),
                            drivers=raw.get("drivers", []),
                        )

                        insight = ProactiveInsight(
                            user_id=user.id,
                            dataset_id=dataset.id,
                            metric_name=raw["metric_name"],
                            insight_type=raw["insight_type"],
                            change_pct=raw.get("change_pct"),
                            current_value=raw.get("current_value"),
                            previous_value=raw.get("previous_value"),
                            drivers=raw.get("drivers", []),
                            narrative=narrative,
                            severity=raw.get("severity", "info"),
                            sent_via=[],
                        )
                        db.add(insight)
                        db.flush()  # get insight.id before dispatch

                        sent_via = await _dispatch_insight(user, config, insight, db)
                        insight.sent_via = sent_via
                        stats["insights_generated"] += 1

                stats["users_scanned"] += 1
                db.commit()

            except Exception as e:
                logger.error(f"Error scanning user {config.user_id}: {e}", exc_info=True)
                stats["errors"] += 1
                db.rollback()

    finally:
        db.close()

    logger.info(f"Proactive scan complete: {stats}")
    return stats


def ensure_default_config(user_id: str, db: Session) -> "ProactiveConfig":
    """Create default ProactiveConfig for a user if it doesn't exist."""
    config = db.query(ProactiveConfig).filter(ProactiveConfig.user_id == user_id).first()
    if not config:
        config = ProactiveConfig(user_id=user_id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config
