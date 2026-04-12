"""
AI Models Router — expose multi-model LLM status, usage analytics,
and model testing endpoints.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.database import get_db, LLMUsageLog
from security.auth import get_current_user
from services.llm_router import llm_router

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────

class ModelTestRequest(BaseModel):
    model_key: str
    prompt: str
    system: str = "You are a helpful AI assistant."
    max_tokens: int = 200


class ModelTestResponse(BaseModel):
    model_key: str
    model_name: str
    provider: str
    response: str
    latency_ms: int
    success: bool


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/models")
async def list_models(current_user=Depends(get_current_user)):
    """List all AI models with availability and health status."""
    return {
        "models": llm_router.get_models_status(),
        "provider_availability": llm_router._provider_available,
    }


@router.post("/test-model", response_model=ModelTestResponse)
async def test_model(req: ModelTestRequest, current_user=Depends(get_current_user)):
    """Test a specific model with a custom prompt."""
    from services.llm_router import ALL_MODELS
    import time

    cfg = ALL_MODELS.get(req.model_key)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Model '{req.model_key}' not found")

    if not llm_router._provider_available.get(cfg.provider, False):
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{cfg.provider}' not configured — add the API key to .env",
        )

    start = time.time()
    try:
        if cfg.provider == "openai":
            result = llm_router._complete_openai(cfg.model_id, req.system, req.prompt, req.max_tokens)
        elif cfg.provider == "anthropic":
            result = llm_router._complete_anthropic(cfg.model_id, req.system, req.prompt, req.max_tokens)
        elif cfg.provider == "google":
            result = llm_router._complete_google(cfg.model_id, req.system, req.prompt, req.max_tokens)
        elif cfg.provider == "ollama":
            result = llm_router._complete_ollama(req.system, req.prompt, req.max_tokens)
        else:
            result = llm_router._rule_based(req.system, req.prompt)
        latency_ms = int((time.time() - start) * 1000)
        return ModelTestResponse(
            model_key=req.model_key,
            model_name=cfg.name,
            provider=cfg.provider,
            response=result,
            latency_ms=latency_ms,
            success=True,
        )
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        return ModelTestResponse(
            model_key=req.model_key,
            model_name=cfg.name,
            provider=cfg.provider,
            response=f"Error: {str(e)}",
            latency_ms=latency_ms,
            success=False,
        )


@router.get("/usage")
async def get_usage(
    days: int = 30,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User's LLM usage and cost analytics for the past N days."""
    since = datetime.utcnow() - timedelta(days=days)
    logs = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.user_id == current_user["sub"], LLMUsageLog.created_at >= since)
        .all()
    )

    total_cost = sum(l.cost_usd or 0 for l in logs)
    total_tokens = sum((l.prompt_tokens or 0) + (l.completion_tokens or 0) for l in logs)
    total_calls = len(logs)

    by_model: dict = {}
    for l in logs:
        key = l.model
        if key not in by_model:
            by_model[key] = {"calls": 0, "tokens": 0, "cost_usd": 0.0, "provider": l.provider}
        by_model[key]["calls"] += 1
        by_model[key]["tokens"] += (l.prompt_tokens or 0) + (l.completion_tokens or 0)
        by_model[key]["cost_usd"] += l.cost_usd or 0

    return {
        "period_days": days,
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 5),
        "by_model": by_model,
    }


@router.get("/usage/summary")
async def get_usage_summary(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate cost by model and day (last 30 days) for billing dashboard."""
    since = datetime.utcnow() - timedelta(days=30)
    logs = (
        db.query(LLMUsageLog)
        .filter(LLMUsageLog.user_id == current_user["sub"], LLMUsageLog.created_at >= since)
        .order_by(LLMUsageLog.created_at)
        .all()
    )

    # Group by day + model
    daily: dict = {}
    for l in logs:
        day = l.created_at.strftime("%Y-%m-%d") if l.created_at else "unknown"
        key = f"{day}|{l.model}"
        if key not in daily:
            daily[key] = {"date": day, "model": l.model, "provider": l.provider, "calls": 0, "cost_usd": 0.0}
        daily[key]["calls"] += 1
        daily[key]["cost_usd"] += l.cost_usd or 0

    return {"daily_breakdown": list(daily.values())}
