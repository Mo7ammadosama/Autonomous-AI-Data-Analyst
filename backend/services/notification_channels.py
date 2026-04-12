"""
Multi-channel notification dispatcher — delivers alert and report notifications
to Slack, Microsoft Teams, and Telegram in addition to email.

All HTTP calls use httpx.AsyncClient (already in requirements.txt).
No new packages required.
"""

import logging
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)


class EmailChannel:
    """Send email notifications via SMTP (configured via env vars)."""

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> bool:
        """Send an email. Requires SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD env vars."""
        import os
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        from_email = os.getenv("FROM_EMAIL", smtp_user)

        if not smtp_host or not smtp_user:
            logger.warning("EmailChannel: SMTP_HOST or SMTP_USER not configured — skipping email send")
            return False

        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to
            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to], msg.as_string())
            logger.info(f"Email sent to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"EmailChannel send failed to {to}: {e}")
            return False


class SlackChannel:
    """Send rich messages to Slack via Incoming Webhooks (Block Kit format)."""

    async def send(
        self,
        webhook_url: str,
        title: str,
        message: str,
        color: str = "#4f46e5",  # indigo default
    ) -> bool:
        if not webhook_url:
            return False
        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": f"🔔 {title}"},
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": message},
                        },
                        {
                            "type": "context",
                            "elements": [{"type": "mrkdwn", "text": "Sent by *DataMind AI Analytics*"}],
                        },
                    ],
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            return False


class TeamsChannel:
    """Send Adaptive Card messages to Microsoft Teams via Incoming Webhook."""

    async def send(
        self,
        webhook_url: str,
        title: str,
        message: str,
    ) -> bool:
        if not webhook_url:
            return False
        # Microsoft Teams uses the legacy "MessageCard" format for webhooks
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": "4f46e5",
            "title": f"🔔 {title}",
            "text": message,
            "potentialAction": [],
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Teams notification failed: {e}")
            return False


class TelegramChannel:
    """Send messages via the Telegram Bot API."""

    BASE_URL = "https://api.telegram.org"

    async def send(
        self,
        bot_token: str,
        chat_id: str,
        message: str,
    ) -> bool:
        if not bot_token or not chat_id:
            return False
        url = f"{self.BASE_URL}/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return False


class NotificationDispatcher:
    """
    Dispatches a notification to all enabled channels for an alert.

    channel_configs is a list of dicts:
      [
        {"type": "slack", "webhook_url": "https://hooks.slack.com/..."},
        {"type": "teams", "webhook_url": "https://outlook.office.com/..."},
        {"type": "telegram", "bot_token": "...", "chat_id": "..."},
      ]
    """

    def __init__(self):
        self._slack = SlackChannel()
        self._teams = TeamsChannel()
        self._telegram = TelegramChannel()

    async def dispatch(
        self,
        channel_configs: List[Dict[str, Any]],
        title: str,
        message: str,
        color: str = "#ef4444",  # red for alerts by default
    ) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for cfg in channel_configs:
            ch_type = cfg.get("type", "")
            if ch_type == "slack":
                results["slack"] = await self._slack.send(
                    cfg.get("webhook_url", ""), title, message, color
                )
            elif ch_type == "teams":
                results["teams"] = await self._teams.send(
                    cfg.get("webhook_url", ""), title, message
                )
            elif ch_type == "telegram":
                results["telegram"] = await self._telegram.send(
                    cfg.get("bot_token", ""), cfg.get("chat_id", ""), f"*{title}*\n\n{message}"
                )
        return results

    def build_channels_from_alert(self, alert) -> List[Dict[str, Any]]:
        """
        Build channel_configs list from an Alert ORM object.
        Used in alert_service.py after an alert is triggered.
        """
        channels = []
        if getattr(alert, "notify_slack", False) and alert.slack_webhook_url:
            channels.append({"type": "slack", "webhook_url": alert.slack_webhook_url})
        if getattr(alert, "notify_teams", False) and alert.teams_webhook_url:
            channels.append({"type": "teams", "webhook_url": alert.teams_webhook_url})
        if getattr(alert, "notify_telegram", False) and alert.telegram_bot_token and alert.telegram_chat_id:
            channels.append({
                "type": "telegram",
                "bot_token": alert.telegram_bot_token,
                "chat_id": alert.telegram_chat_id,
            })
        return channels


# ── Singleton ─────────────────────────────────────────────────────
notification_dispatcher = NotificationDispatcher()
