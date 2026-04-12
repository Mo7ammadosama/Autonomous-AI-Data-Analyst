"""
Real-Time Streaming Router — Grafana style sub-second dashboard refresh.

Manages DataStream configurations and serves live metric data
via WebSocket connections.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, DataStream, Dataset
from security.auth import get_current_user

router = APIRouter(prefix="/api/streams", tags=["Real-Time Streaming"])
logger = logging.getLogger(__name__)

# Active stream connections: {stream_id: [websocket, ...]}
_active_connections: Dict[str, List[WebSocket]] = {}


# ─── Schemas ───────────────────────────────────────────────────

class StreamCreate(BaseModel):
    name: str
    description: Optional[str] = None
    source_type: str                            # dataset | connection | api
    source_id: Optional[str] = None
    query: Optional[str] = None                # SQL or JSON path
    refresh_interval_seconds: int = 30          # 1 | 5 | 30 | 60
    transformations: Optional[List[Dict]] = []


class StreamUpdate(BaseModel):
    name: Optional[str] = None
    refresh_interval_seconds: Optional[int] = None
    query: Optional[str] = None
    is_active: Optional[bool] = None


# ─── CRUD Endpoints ────────────────────────────────────────────

@router.post("/create")
def create_stream(
    body: StreamCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new real-time data stream configuration."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]

    if body.refresh_interval_seconds < 1:
        raise HTTPException(status_code=400, detail="Minimum refresh interval is 1 second")
    if body.source_type not in ("dataset", "connection", "api"):
        raise HTTPException(status_code=400, detail="source_type must be dataset | connection | api")

    stream = DataStream(
        user_id=uid,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        source_id=body.source_id,
        query=body.query,
        refresh_interval_seconds=body.refresh_interval_seconds,
        transformations=body.transformations,
    )
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return _stream_out(stream)


@router.get("/")
def list_streams(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all data streams for the current user."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    streams = (
        db.query(DataStream)
        .filter(DataStream.user_id == uid)
        .order_by(DataStream.created_at.desc())
        .all()
    )
    return [_stream_out(s) for s in streams]


@router.get("/{stream_id}")
def get_stream(
    stream_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a stream configuration by ID."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    stream = db.query(DataStream).filter(
        DataStream.id == stream_id, DataStream.user_id == uid
    ).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    return {**_stream_out(stream), "active_subscribers": len(_active_connections.get(stream_id, []))}


@router.put("/{stream_id}")
def update_stream(
    stream_id: str,
    body: StreamUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a stream configuration."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    stream = db.query(DataStream).filter(
        DataStream.id == stream_id, DataStream.user_id == uid
    ).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    for k, v in body.dict(exclude_none=True).items():
        setattr(stream, k, v)
    db.commit()
    return _stream_out(stream)


@router.delete("/{stream_id}")
def delete_stream(
    stream_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a stream."""
    uid = current_user.id if hasattr(current_user, "id") else current_user["sub"]
    stream = db.query(DataStream).filter(
        DataStream.id == stream_id, DataStream.user_id == uid
    ).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    db.delete(stream)
    db.commit()
    return {"status": "deleted"}


# ─── WebSocket Streaming ───────────────────────────────────────

@router.websocket("/ws/{stream_id}")
async def stream_websocket(
    websocket: WebSocket,
    stream_id: str,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time data streaming.
    Client connects → receives data at configured interval.

    Protocol:
      Server → client: {"type": "data", "stream_id": "...", "data": [...], "timestamp": "..."}
      Server → client: {"type": "heartbeat", "timestamp": "..."}
      Client → server: {"type": "ping"} → server replies {"type": "pong"}
    """
    await websocket.accept()
    logger.info(f"Stream WebSocket connected: {stream_id}")

    # Add to active connections
    if stream_id not in _active_connections:
        _active_connections[stream_id] = []
    _active_connections[stream_id].append(websocket)

    try:
        # Load stream config
        db = next(get_db())
        stream = db.query(DataStream).filter(DataStream.id == stream_id).first()
        db.close()

        if not stream or not stream.is_active:
            await websocket.send_json({"type": "error", "message": "Stream not found or inactive"})
            return

        interval = max(1, stream.refresh_interval_seconds)

        # Streaming loop
        while True:
            # Check for incoming messages (non-blocking)
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            # Fetch and push new data
            try:
                payload = await _fetch_stream_data(stream_id, stream.source_type, stream.source_id, stream.query)
                await websocket.send_json({
                    "type": "data",
                    "stream_id": stream_id,
                    "data": payload,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                # Update last_pushed_at
                db2 = next(get_db())
                s2 = db2.query(DataStream).filter(DataStream.id == stream_id).first()
                if s2:
                    s2.last_pushed_at = datetime.utcnow()
                    db2.commit()
                db2.close()
            except Exception as e:
                logger.warning(f"Stream data fetch error for {stream_id}: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

            await asyncio.sleep(interval)

    except WebSocketDisconnect:
        logger.info(f"Stream WebSocket disconnected: {stream_id}")
    finally:
        if stream_id in _active_connections:
            try:
                _active_connections[stream_id].remove(websocket)
            except ValueError:
                pass
            if not _active_connections[stream_id]:
                del _active_connections[stream_id]


async def _fetch_stream_data(
    stream_id: str,
    source_type: str,
    source_id: Optional[str],
    query: Optional[str],
) -> List[Dict[str, Any]]:
    """Fetch the latest data for a stream based on its source type."""
    if source_type == "dataset" and source_id:
        return await _fetch_dataset_data(source_id, query)
    return [{"timestamp": datetime.utcnow().isoformat(), "value": 0}]


async def _fetch_dataset_data(dataset_id: str, query: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch aggregate stats from a dataset — simulates live metric."""
    try:
        db = next(get_db())
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        db.close()
        if not dataset or not dataset.file_path:
            return []
        import os
        import pandas as pd
        if not os.path.exists(dataset.file_path):
            return []
        df = pd.read_csv(dataset.file_path, nrows=1000) if dataset.file_path.endswith(".csv") else None
        if df is None:
            return []
        numeric = df.select_dtypes(include="number")
        stats = []
        for col in numeric.columns[:5]:
            stats.append({
                "metric": col,
                "value": float(numeric[col].iloc[-1]) if len(numeric) > 0 else 0,
                "mean": float(numeric[col].mean()),
                "max": float(numeric[col].max()),
                "timestamp": datetime.utcnow().isoformat(),
            })
        return stats
    except Exception as e:
        logger.warning(f"Dataset stream fetch error: {e}")
        return []


def _stream_out(s: DataStream) -> Dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "source_type": s.source_type,
        "source_id": s.source_id,
        "refresh_interval_seconds": s.refresh_interval_seconds,
        "is_active": s.is_active,
        "subscriber_count": s.subscriber_count,
        "last_pushed_at": s.last_pushed_at,
        "created_at": s.created_at,
    }
