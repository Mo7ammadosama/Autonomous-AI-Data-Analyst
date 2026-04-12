"""
Real-time WebSocket endpoints.

Auth: JWT passed as query param ?token=... (browsers cannot set
custom headers during WebSocket upgrades).

Rooms:
  - dashboard:{dashboard_id}  — live metric refresh for a specific dashboard
  - user:{user_id}:alerts      — real-time alert notifications per user
  - user:{user_id}:notifs      — in-app notification delivery
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_ws_token(token: str) -> Optional[dict]:
    """Validate the JWT token passed as a query parameter."""
    if not token:
        return None
    try:
        from security.auth import verify_token
        return verify_token(token)
    except Exception:
        return None


@router.websocket("/ws/dashboard/{dashboard_id}")
async def ws_dashboard(
    websocket: WebSocket,
    dashboard_id: str,
    token: str = Query(default=""),
):
    """
    Live dashboard updates.
    Clients receive metric_update events when data refreshes.
    """
    user = _verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    room_id = f"dashboard:{dashboard_id}"
    await manager.connect(websocket, room_id)

    # Send welcome event
    await manager.send_to(websocket, {
        "type": "connected",
        "room": room_id,
        "message": "Live dashboard connected. You will receive real-time updates.",
    })

    try:
        while True:
            # Keep connection alive — wait for client pings or close
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await manager.send_to(websocket, {"type": "pong"})
    except asyncio.TimeoutError:
        # Send keepalive heartbeat
        try:
            await manager.send_to(websocket, {"type": "heartbeat"})
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Dashboard WS error: {e}")
    finally:
        manager.disconnect(websocket, room_id)


@router.websocket("/ws/alerts")
async def ws_alerts(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    """
    Real-time alert trigger stream for the current user.
    Replaces polling /api/alerts/*/logs.
    """
    user = _verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    user_id = user.get("sub", "")
    room_id = f"alerts:{user_id}"
    await manager.connect(websocket, room_id)
    await manager.send_to(websocket, {"type": "connected", "room": room_id})

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await manager.send_to(websocket, {"type": "pong"})
    except asyncio.TimeoutError:
        try:
            await manager.send_to(websocket, {"type": "heartbeat"})
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Alerts WS error: {e}")
    finally:
        manager.disconnect(websocket, room_id)


@router.websocket("/ws/notifications")
async def ws_notifications(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    """
    Real-time in-app notification delivery.
    Sends notification objects directly so UI doesn't need to poll.
    """
    user = _verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    user_id = user.get("sub", "")
    room_id = f"notifications:{user_id}"
    await manager.connect(websocket, room_id)
    await manager.send_to(websocket, {"type": "connected", "room": room_id})

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await manager.send_to(websocket, {"type": "pong"})
    except asyncio.TimeoutError:
        try:
            await manager.send_to(websocket, {"type": "heartbeat"})
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"Notifications WS error: {e}")
    finally:
        manager.disconnect(websocket, room_id)
