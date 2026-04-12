"""
WebSocket Connection Manager — real-time push to connected clients.

Supports room-based broadcasting (e.g., per-dashboard, per-user).
"""

import logging
from collections import defaultdict
from typing import Dict, Set, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections organized by room IDs."""

    def __init__(self):
        # room_id → set of active WebSocket connections
        self._rooms: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        self._rooms[room_id].add(websocket)
        logger.debug(f"WS connected: room={room_id}, total={len(self._rooms[room_id])}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        self._rooms[room_id].discard(websocket)
        if not self._rooms[room_id]:
            del self._rooms[room_id]
        logger.debug(f"WS disconnected: room={room_id}")

    async def broadcast(self, room_id: str, message: Dict[str, Any]):
        """Send a JSON message to all connections in a room."""
        dead: Set[WebSocket] = set()
        for ws in list(self._rooms.get(room_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._rooms[room_id].discard(ws)

    async def broadcast_all(self, message: Dict[str, Any]):
        """Send a JSON message to every connected client in every room."""
        for room_id in list(self._rooms.keys()):
            await self.broadcast(room_id, message)

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send a JSON message to a single WebSocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.debug(f"Failed to send WS message: {e}")

    def room_count(self, room_id: str) -> int:
        return len(self._rooms.get(room_id, set()))

    def total_connections(self) -> int:
        return sum(len(v) for v in self._rooms.values())


# ── Singleton used by all routers ─────────────────────────────────
manager = ConnectionManager()
