"""
Webhooks router — register HTTP endpoints to receive alert and platform events.

Supported events:
  alert.triggered   — fired when an alert condition is met
  report.sent       — fired after a scheduled report is delivered
  dataset.uploaded  — fired when a dataset upload completes
  insight.ready     — fired when auto-insights generation finishes

Delivery: POST to the webhook URL with JSON payload and X-DataMind-Signature header
(HMAC-SHA256 of the payload with the webhook secret).
"""

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from models.database import get_db, Webhook
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_EVENTS = {
    "alert.triggered",
    "report.sent",
    "dataset.uploaded",
    "insight.ready",
    "pipeline.complete",
}


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


def _sign_payload(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def deliver_webhook(webhook_id: str, event: str, payload: dict, db: Session):
    """Deliver a webhook event to the registered URL (called from background tasks)."""
    wh = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.is_active == True).first()
    if not wh:
        return
    body = json.dumps({"event": event, "data": payload}).encode()
    headers = {"Content-Type": "application/json", "X-DataMind-Event": event}
    if wh.secret:
        headers["X-DataMind-Signature"] = _sign_payload(wh.secret, body)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(wh.url, content=body, headers=headers)
            resp.raise_for_status()
            from datetime import datetime
            wh.last_triggered_at = datetime.utcnow()
            wh.failure_count = 0
            db.commit()
    except Exception as e:
        logger.warning(f"Webhook {webhook_id} delivery failed: {e}")
        wh.failure_count = (wh.failure_count or 0) + 1
        if wh.failure_count >= 10:
            wh.is_active = False
            logger.warning(f"Webhook {webhook_id} disabled after 10 consecutive failures")
        db.commit()


async def fire_event(event: str, payload: dict, user_id: str, db: Session,
                     background_tasks: Optional[BackgroundTasks] = None):
    """Fire an event to all matching active webhooks for a user."""
    webhooks = db.query(Webhook).filter(
        Webhook.user_id == user_id,
        Webhook.is_active == True,
    ).all()
    for wh in webhooks:
        if event in (wh.events or []):
            if background_tasks:
                background_tasks.add_task(deliver_webhook, wh.id, event, payload, db)
            else:
                await deliver_webhook(wh.id, event, payload, db)


@router.get("/")
async def list_webhooks(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hooks = db.query(Webhook).filter(Webhook.user_id == current_user["sub"]).all()
    return [
        {
            "id": h.id,
            "name": h.name,
            "url": h.url,
            "events": h.events or [],
            "is_active": h.is_active,
            "failure_count": h.failure_count,
            "last_triggered_at": h.last_triggered_at.isoformat() if h.last_triggered_at else None,
            "created_at": h.created_at.isoformat(),
        }
        for h in hooks
    ]


@router.post("/", status_code=201)
async def create_webhook(
    req: WebhookCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invalid = [e for e in req.events if e not in VALID_EVENTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid events: {invalid}. Valid: {sorted(VALID_EVENTS)}")
    wh = Webhook(
        id=str(uuid.uuid4()),
        user_id=current_user["sub"],
        name=req.name,
        url=req.url,
        events=req.events,
        secret=req.secret or secrets.token_hex(16),
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return {
        "id": wh.id, "name": wh.name, "url": wh.url, "events": wh.events,
        "secret": wh.secret, "is_active": wh.is_active, "created_at": wh.created_at.isoformat(),
    }


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    req: WebhookUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == current_user["sub"]).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if req.name is not None:
        wh.name = req.name
    if req.url is not None:
        wh.url = req.url
    if req.events is not None:
        invalid = [e for e in req.events if e not in VALID_EVENTS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid events: {invalid}")
        wh.events = req.events
    if req.is_active is not None:
        wh.is_active = req.is_active
        if req.is_active:
            wh.failure_count = 0
    db.commit()
    return {"message": "Webhook updated", "id": wh.id}


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wh = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == current_user["sub"]).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(wh)
    db.commit()


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a test payload to the webhook URL to verify connectivity."""
    wh = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.user_id == current_user["sub"]).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    test_payload = {"event": "webhook.test", "data": {"message": "DataMind webhook test", "webhook_id": wh.id}}
    body = json.dumps(test_payload).encode()
    headers = {"Content-Type": "application/json", "X-DataMind-Event": "webhook.test"}
    if wh.secret:
        headers["X-DataMind-Signature"] = _sign_payload(wh.secret, body)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(wh.url, content=body, headers=headers)
        return {"success": True, "status_code": resp.status_code, "message": "Test delivery successful"}
    except Exception as e:
        return {"success": False, "error": str(e), "message": "Test delivery failed"}


@router.get("/events")
async def list_valid_events():
    """List all supported webhook event types."""
    return {"events": sorted(VALID_EVENTS)}
