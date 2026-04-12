"""
Personalized AI Digest Generator — Tableau Pulse + Domo style.

Generates daily/weekly email + Slack digests personalized per user:
- Top metric anomalies detected
- Biggest % changes since last period
- AI-suggested questions to explore
- Data quality updates
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# HTML email template
_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 0; }}
  .container {{ max-width: 600px; margin: 0 auto; padding: 24px; }}
  .header {{ background: linear-gradient(135deg, #4f46e5, #7c3aed); border-radius: 12px; padding: 24px; margin-bottom: 24px; text-align: center; }}
  .header h1 {{ margin: 0; font-size: 24px; color: #fff; }}
  .header p {{ margin: 8px 0 0; color: rgba(255,255,255,0.8); font-size: 14px; }}
  .card {{ background: #1e293b; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
  .card h2 {{ margin: 0 0 12px; font-size: 16px; color: #a5b4fc; }}
  .insight-row {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
  .insight-row:last-child {{ border-bottom: none; }}
  .metric-name {{ font-weight: 600; color: #f1f5f9; font-size: 14px; }}
  .metric-value {{ font-size: 14px; color: #64748b; }}
  .change-up {{ color: #22c55e; font-weight: 700; }}
  .change-down {{ color: #ef4444; font-weight: 700; }}
  .suggestion {{ background: rgba(99,102,241,0.1); border-left: 3px solid #6366f1; padding: 10px 14px; margin-bottom: 8px; border-radius: 4px; font-size: 14px; color: #c7d2fe; }}
  .footer {{ text-align: center; margin-top: 24px; font-size: 12px; color: #475569; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }}
  .badge-warning {{ background: #92400e; color: #fcd34d; }}
  .badge-critical {{ background: #7f1d1d; color: #fca5a5; }}
  .badge-info {{ background: #1e3a5f; color: #93c5fd; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>⚡ DataMind Intelligence Digest</h1>
    <p>{period_label} · {date_label}</p>
  </div>

  {anomalies_section}
  {top_changes_section}
  {suggestions_section}
  {data_quality_section}

  <div class="footer">
    <p>You're receiving this because you have digest delivery enabled.</p>
    <p><a href="{unsubscribe_url}" style="color: #6366f1;">Unsubscribe</a> · <a href="{app_url}/proactive" style="color: #6366f1;">View in App</a></p>
    <p>DataMind AI Analytics Platform</p>
  </div>
</div>
</body>
</html>
"""


def _anomalies_html(anomalies: List[Dict]) -> str:
    if not anomalies:
        return ""
    rows = ""
    for a in anomalies[:5]:
        sev = a.get("severity", "info")
        badge = f'<span class="badge badge-{sev}">{sev}</span>'
        rows += f"""
        <div class="insight-row">
          <div>
            <div class="metric-name">{a.get('metric_name', 'Unknown')} {badge}</div>
            <div class="metric-value">{a.get('narrative', '')[:120]}</div>
          </div>
        </div>"""
    return f'<div class="card"><h2>🚨 Anomalies Detected ({len(anomalies)})</h2>{rows}</div>'


def _top_changes_html(changes: List[Dict]) -> str:
    if not changes:
        return ""
    rows = ""
    for c in changes[:5]:
        pct = c.get("change_pct", 0) or 0
        cls = "change-up" if pct > 0 else "change-down"
        arrow = "▲" if pct > 0 else "▼"
        rows += f"""
        <div class="insight-row">
          <span class="metric-name">{c.get('metric_name', 'Metric')}</span>
          <span class="{cls}">{arrow} {abs(pct):.1f}%</span>
        </div>"""
    return f'<div class="card"><h2>📊 Biggest Changes</h2>{rows}</div>'


def _suggestions_html(suggestions: List[str]) -> str:
    if not suggestions:
        return ""
    items = "".join(f'<div class="suggestion">💡 {s}</div>' for s in suggestions[:4])
    return f'<div class="card"><h2>🤖 AI-Suggested Questions</h2>{items}</div>'


def _quality_html(quality_issues: List[Dict]) -> str:
    if not quality_issues:
        return ""
    rows = ""
    for q in quality_issues[:3]:
        rows += f"""
        <div class="insight-row">
          <div>
            <div class="metric-name">{q.get('dataset_name', 'Dataset')}</div>
            <div class="metric-value">{q.get('issue', '')}</div>
          </div>
        </div>"""
    return f'<div class="card"><h2>⚠️ Data Quality</h2>{rows}</div>'


def build_digest_html(
    user_name: str,
    frequency: str,
    anomalies: List[Dict],
    top_changes: List[Dict],
    suggestions: List[str],
    quality_issues: List[Dict],
    app_url: str = "http://localhost:3000",
    unsubscribe_url: str = "",
) -> str:
    """Build the full HTML digest email."""
    period_label = "Daily Digest" if frequency == "daily" else "Weekly Digest"
    date_label = datetime.utcnow().strftime("%B %d, %Y")
    return _EMAIL_TEMPLATE.format(
        period_label=period_label,
        date_label=date_label,
        anomalies_section=_anomalies_html(anomalies),
        top_changes_section=_top_changes_html(top_changes),
        suggestions_section=_suggestions_html(suggestions),
        data_quality_section=_quality_html(quality_issues),
        app_url=app_url,
        unsubscribe_url=unsubscribe_url or f"{app_url}/settings",
    )


def build_slack_digest(
    anomalies: List[Dict],
    top_changes: List[Dict],
    suggestions: List[str],
    frequency: str = "weekly",
) -> Dict[str, Any]:
    """Build Slack Block Kit digest message."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"⚡ DataMind {'Daily' if frequency == 'daily' else 'Weekly'} Intelligence Digest"},
        },
        {"type": "divider"},
    ]

    if anomalies:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🚨 {len(anomalies)} Anomaly{'s' if len(anomalies) != 1 else ''} Detected*\n"
                        + "\n".join(f"• *{a.get('metric_name')}*: {a.get('narrative', '')[:100]}" for a in anomalies[:3]),
            },
        })

    if top_changes:
        change_text = "\n".join(
            f"• *{c.get('metric_name')}*: {'▲' if (c.get('change_pct') or 0) > 0 else '▼'} {abs(c.get('change_pct', 0)):.1f}%"
            for c in top_changes[:3]
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📊 Biggest Changes*\n{change_text}"},
        })

    if suggestions:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*💡 Questions to Explore*\n" + "\n".join(f"• {s}" for s in suggestions[:3])},
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "View Intelligence Feed"}, "url": "http://localhost:3000/proactive"},
        ],
    })
    return {"blocks": blocks}


async def collect_digest_data(user_id: str, days: int = 7) -> Dict[str, Any]:
    """Collect all data needed for the digest from the database."""
    from models.database import SessionLocal, ProactiveInsight, Dataset
    from datetime import timedelta

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Recent proactive insights
        insights = (
            db.query(ProactiveInsight)
            .filter(
                ProactiveInsight.user_id == user_id,
                ProactiveInsight.created_at >= cutoff,
            )
            .order_by(ProactiveInsight.created_at.desc())
            .limit(20)
            .all()
        )

        anomalies = [
            {"metric_name": i.metric_name, "narrative": i.narrative, "severity": i.severity}
            for i in insights if i.insight_type == "anomaly"
        ]
        top_changes = [
            {"metric_name": i.metric_name, "change_pct": i.change_pct}
            for i in insights if i.insight_type == "trend_shift" and i.change_pct is not None
        ]
        top_changes.sort(key=lambda x: abs(x.get("change_pct") or 0), reverse=True)

        # AI-suggested questions
        suggestions = _generate_suggestions(insights)

        # Data quality
        quality_issues = [
            {"dataset_name": "Dataset", "issue": i.narrative or "Quality issue detected"}
            for i in insights if i.insight_type == "data_quality"
        ]

        return {
            "anomalies": anomalies,
            "top_changes": top_changes[:5],
            "suggestions": suggestions,
            "quality_issues": quality_issues,
            "total_insights": len(insights),
        }
    finally:
        db.close()


def _generate_suggestions(insights: list) -> List[str]:
    """Generate follow-up question suggestions based on insights."""
    suggestions = []
    seen_metrics = set()
    for ins in insights:
        if ins.metric_name and ins.metric_name not in seen_metrics:
            seen_metrics.add(ins.metric_name)
            if ins.insight_type == "trend_shift":
                suggestions.append(f"What caused the change in {ins.metric_name}?")
            elif ins.insight_type == "anomaly":
                suggestions.append(f"Which segments are driving the {ins.metric_name} anomaly?")
            elif ins.insight_type == "record_high":
                suggestions.append(f"What contributed to the record high in {ins.metric_name}?")
    if not suggestions:
        suggestions = [
            "What are the top performing metrics this week?",
            "Which datasets have the most anomalies?",
            "Show me the trend for my most important KPIs.",
        ]
    return suggestions[:4]


async def send_digest_to_user(user_id: str, config) -> Dict[str, Any]:
    """
    Collect digest data and send via configured channels.
    Called by the Celery beat task.
    """
    from models.database import SessionLocal, User, DigestConfig

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}

        frequency = config.frequency or "weekly"
        days = 1 if frequency == "daily" else 7

        data = await collect_digest_data(user_id, days=days)
        sent_via = []

        # Email
        if config.delivery_email or user.email:
            try:
                html = build_digest_html(
                    user_name=user.username,
                    frequency=frequency,
                    **{k: v for k, v in data.items() if k in ("anomalies", "top_changes", "suggestions", "quality_issues")},
                )
                from services.notification_channels import EmailChannel
                email_ch = EmailChannel()
                await email_ch.send(
                    to=config.delivery_email or user.email,
                    subject=f"DataMind {'Daily' if frequency == 'daily' else 'Weekly'} Intelligence Digest",
                    body=html,
                    html=True,
                )
                sent_via.append("email")
            except Exception as e:
                logger.warning(f"Digest email failed for {user_id}: {e}")

        # Slack
        if config.delivery_slack and config.slack_webhook_url:
            try:
                from services.notification_channels import SlackChannel
                slack_msg = build_slack_digest(
                    anomalies=data["anomalies"],
                    top_changes=data["top_changes"],
                    suggestions=data["suggestions"],
                    frequency=frequency,
                )
                import httpx
                async with httpx.AsyncClient() as client:
                    await client.post(config.slack_webhook_url, json=slack_msg, timeout=10)
                sent_via.append("slack")
            except Exception as e:
                logger.warning(f"Digest Slack failed for {user_id}: {e}")

        # Update last_sent_at
        config.last_sent_at = datetime.utcnow()
        db.commit()

        return {"user_id": user_id, "sent_via": sent_via, "insights_count": data["total_insights"]}
    finally:
        db.close()
