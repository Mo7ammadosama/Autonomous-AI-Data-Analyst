"""
Alert Service — evaluate user-defined threshold alerts against dataset values.

Conditions supported:
  gt  (greater than)         column_agg > threshold
  lt  (less than)            column_agg < threshold
  gte (greater than or equal)
  lte (less than or equal)
  eq  (equal)
  anomaly                    statistical anomaly detected in column

Aggregations: mean | sum | max | min | count | latest
"""

import logging
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@datamind.ai")


# ── Aggregation helpers ─────────────────────────────────────────

def _compute_aggregation(series: pd.Series, aggregation: str) -> Optional[float]:
    try:
        s = series.dropna()
        if len(s) == 0:
            return None
        agg_map = {
            "mean": s.mean,
            "sum": s.sum,
            "max": s.max,
            "min": s.min,
            "count": lambda: float(len(s)),
            "latest": lambda: float(s.iloc[-1]),
            "median": s.median,
            "std": s.std,
        }
        fn = agg_map.get(aggregation, s.mean)
        val = fn()
        return float(val)
    except Exception as e:
        logger.debug(f"Aggregation error: {e}")
        return None


def _is_anomaly(series: pd.Series) -> Tuple[bool, Optional[float]]:
    """Z-score based anomaly detection on last value."""
    s = series.dropna()
    if len(s) < 10:
        return False, None
    mean = s.mean()
    std = s.std()
    if std == 0:
        return False, None
    latest = float(s.iloc[-1])
    z_score = abs((latest - mean) / std)
    return z_score > 3.0, latest


# ── Condition evaluator ──────────────────────────────────────────

def evaluate_condition(
    actual_value: Optional[float],
    condition: str,
    threshold: Optional[float],
) -> bool:
    if actual_value is None:
        return False
    condition_map = {
        "gt":  lambda a, t: a > t,
        "lt":  lambda a, t: a < t,
        "gte": lambda a, t: a >= t,
        "lte": lambda a, t: a <= t,
        "eq":  lambda a, t: abs(a - t) < 1e-9,
    }
    fn = condition_map.get(condition)
    if fn and threshold is not None:
        return fn(actual_value, threshold)
    return False


# ── Alert evaluation ─────────────────────────────────────────────

def evaluate_alert(alert, df: pd.DataFrame) -> Tuple[bool, Optional[float], str]:
    """
    Evaluate a single alert against a DataFrame.

    Returns (triggered: bool, actual_value: float|None, message: str)
    """
    col = alert.column_name
    condition = alert.condition
    threshold = alert.threshold
    aggregation = getattr(alert, "aggregation", "mean") or "mean"

    if col not in df.columns:
        return False, None, f"Column '{col}' not found in dataset."

    series = df[col]

    if not pd.api.types.is_numeric_dtype(series):
        return False, None, f"Column '{col}' is not numeric — cannot evaluate threshold."

    if condition == "anomaly":
        triggered, latest = _is_anomaly(series)
        msg = (
            f"Anomaly detected in '{col}': latest value {latest:.4g} is > 3 std deviations from mean."
            if triggered
            else f"No anomaly detected in '{col}'."
        )
        return triggered, latest, msg

    actual = _compute_aggregation(series, aggregation)
    triggered = evaluate_condition(actual, condition, threshold)

    condition_labels = {
        "gt": ">", "lt": "<", "gte": ">=", "lte": "<=", "eq": "=="
    }
    label = condition_labels.get(condition, condition)
    msg = (
        f"Alert triggered: {aggregation}({col}) = {actual:.4g} {label} {threshold}"
        if triggered
        else f"OK: {aggregation}({col}) = {actual:.4g} (threshold: {label} {threshold})"
    )
    return triggered, actual, msg


# ── Email notification ───────────────────────────────────────────

async def send_alert_email(
    recipient: str,
    alert_name: str,
    message: str,
    dataset_name: str = "dataset",
) -> bool:
    """Send an alert notification email asynchronously. Returns True on success."""
    if not SMTP_HOST or not SMTP_USER:
        logger.info("SMTP not configured — skipping email notification")
        return False

    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        subject = f"[DataMind Alert] {alert_name}"
        body = f"""
<html><body style="font-family: sans-serif; color: #1e293b;">
<div style="max-width:600px;margin:0 auto;padding:24px;background:#f8fafc;border-radius:12px;">
  <h2 style="color:#6366f1;">&#9888; DataMind Alert Triggered</h2>
  <p><strong>Alert:</strong> {alert_name}</p>
  <p><strong>Dataset:</strong> {dataset_name}</p>
  <p><strong>Details:</strong> {message}</p>
  <p style="color:#64748b;font-size:12px;margin-top:24px;">
    Sent by DataMind AI Analytics Platform ·
    <a href="#" style="color:#6366f1;">Manage alerts</a>
  </p>
</div>
</body></html>
"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = recipient
        msg.attach(MIMEText(body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=False,
            start_tls=True,
        )
        logger.info(f"Alert email sent to {recipient}")
        return True

    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        return False


# ── Bulk alert runner ────────────────────────────────────────────

class AlertService:
    """Evaluates all active alerts for a dataset and records triggers."""

    def evaluate_all(
        self,
        alerts: List,
        df: pd.DataFrame,
        dataset_name: str,
        db,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate every alert in `alerts` against the DataFrame.
        Persists AlertLog entries for triggered alerts.
        Returns list of trigger results.
        """
        from models.database import AlertLog

        results = []
        for alert in alerts:
            if not getattr(alert, "is_active", True):
                continue
            triggered, actual_value, message = evaluate_alert(alert, df)

            # Update last_checked
            alert.last_checked = datetime.utcnow()

            if triggered:
                alert.trigger_count = (alert.trigger_count or 0) + 1
                alert.last_triggered = datetime.utcnow()
                alert.status = "fired"

                log_entry = AlertLog(
                    alert_id=alert.id,
                    actual_value=actual_value,
                    message=message,
                    notified=False,
                )
                db.add(log_entry)

                results.append({
                    "alert_id": alert.id,
                    "alert_name": alert.name,
                    "triggered": True,
                    "actual_value": actual_value,
                    "message": message,
                    "email_recipient": alert.email_recipient,
                })

                # Fire-and-forget email if configured
                if alert.notify_email and alert.email_recipient:
                    asyncio.create_task(
                        send_alert_email(
                            alert.email_recipient,
                            alert.name,
                            message,
                            dataset_name,
                        )
                    )

                # Fire-and-forget Slack/Teams/Telegram notifications
                try:
                    from services.notification_channels import notification_dispatcher
                    from services.websocket_manager import manager as ws_manager
                    channels = notification_dispatcher.build_channels_from_alert(alert)
                    if channels:
                        asyncio.create_task(
                            notification_dispatcher.dispatch(channels, alert.name, message)
                        )
                    # Push to WebSocket real-time alert stream
                    asyncio.create_task(
                        ws_manager.broadcast(
                            f"alerts:{alert.user_id}",
                            {
                                "type": "alert_triggered",
                                "alert_id": alert.id,
                                "alert_name": alert.name,
                                "message": message,
                                "actual_value": actual_value,
                            },
                        )
                    )
                except Exception as _ws_err:
                    logger.debug(f"WS/channel notification error: {_ws_err}")
            else:
                alert.status = "active"
                results.append({
                    "alert_id": alert.id,
                    "alert_name": alert.name,
                    "triggered": False,
                    "actual_value": actual_value,
                    "message": message,
                })

        db.commit()
        return results
