"""
Universal AI Copilot Router
POST /api/copilot/ask  — main copilot endpoint
GET  /api/copilot/intents — list available intents
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import logging

from models.database import get_db
from security.auth import get_current_user
from services.llm_service import LLMService
from services.copilot import handle_copilot_request, classify_intent

router = APIRouter()
logger = logging.getLogger(__name__)

_llm = LLMService()


class CopilotRequest(BaseModel):
    question: str
    dataset_id: Optional[str] = None  # optional — copilot works without dataset too


@router.post("/ask")
async def copilot_ask(
    req: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Universal copilot endpoint.
    Routes to the appropriate service based on intent.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = handle_copilot_request(
            question=req.question,
            dataset_id=req.dataset_id,
            db=db,
            current_user=current_user,
            llm_service=_llm,
        )
        return result
    except Exception as e:
        logger.error(f"Copilot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Copilot error: {str(e)}")


@router.get("/intents")
async def list_intents(current_user: dict = Depends(get_current_user)):
    """Return available copilot intents with example prompts."""
    return {
        "intents": [
            {"name": "summary",        "example": "Give me an overview of this dataset"},
            {"name": "forecast",       "example": "Forecast sales for the next 30 days"},
            {"name": "anomaly",        "example": "Detect any unusual patterns or anomalies"},
            {"name": "correlation",    "example": "What are the strongest correlations?"},
            {"name": "recommendation", "example": "What actions should I take based on this data?"},
            {"name": "story",          "example": "Write a data story from this dataset"},
            {"name": "dashboard",      "example": "Create a sales dashboard"},
            {"name": "top_n",          "example": "Show me the top 10 products by revenue"},
            {"name": "comparison",     "example": "Compare revenue across regions"},
            {"name": "trend",          "example": "Show revenue trend over time"},
            {"name": "clean",          "example": "Check data quality and missing values"},
            {"name": "chat",           "example": "What is a good way to analyze this data?"},
        ]
    }


@router.post("/classify")
async def classify_question(
    req: CopilotRequest,
    current_user: dict = Depends(get_current_user),
):
    """Classify a question's intent without executing it."""
    intent = classify_intent(req.question)
    return {"question": req.question, "intent": intent}
