"""
Chat router: AI-powered data conversations with Agentic RAG
"""

import json
import asyncio

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import logging

from models.database import get_db, Dataset, ChatSession, ChatMessage
from services.data_processor import load_dataset
from services.ai_agent import AIDataAnalystAgent
from services.rag_service import RAGService
from services.llm_service import LLMService
from services.llm_router import llm_router
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
agent = AIDataAnalystAgent()

_llm = LLMService()
_rag = RAGService(_llm)


def _detect_language(text: str) -> str:
    """Returns 'arabic' if >30% of chars are Arabic script, else 'english'."""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return "arabic" if len(text) > 0 and arabic_chars / len(text) > 0.3 else "english"


def _build_system_prompt(has_dataset: bool, lang: str) -> str:
    lang_instruction = (
        "أجب دائماً باللغة العربية. كن مباشراً وطبيعياً. لا تستخدم قوائم أو نقاط إلا إذا طُلب منك ذلك صراحةً."
        if lang == "arabic"
        else "Respond in the same language the user writes in. Be direct and conversational — avoid bullet lists unless specifically requested."
    )
    base = (
        f"You are DataMind AI — an expert assistant for data analytics and general questions.\n"
        f"{lang_instruction}\n"
        f"Answer questions directly and concisely. Do NOT describe your own training, architecture, or limitations "
        f"unless explicitly asked. Do NOT start with 'As an AI...' disclaimers. Just answer naturally."
    )
    if has_dataset:
        base += (
            "\n\nThe user has a dataset loaded. For data questions, give specific analytical insights. "
            "For general questions, answer normally."
        )
    return base


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    dataset_id: Optional[str] = None


class SessionCreateRequest(BaseModel):
    dataset_id: Optional[str] = None
    title: Optional[str] = None


@router.post("/sessions")
async def create_session(req: SessionCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    session = ChatSession(
        id=str(uuid.uuid4()),
        title=req.title or "New Analysis",
        dataset_id=req.dataset_id,
        user_id=current_user["sub"],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title, "dataset_id": session.dataset_id}


@router.get("/sessions")
async def list_sessions(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user["sub"]).order_by(ChatSession.created_at.desc()).limit(20).all()
    return [{"id": s.id, "title": s.title, "dataset_id": s.dataset_id, "created_at": s.created_at.isoformat()} for s in sessions]


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user["sub"]).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return [
        {
            "id": m.id, "role": m.role, "content": m.content,
            "charts": m.charts, "code": m.code, "insights": m.insights,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.post("/message")
async def send_message(req: ChatRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Send message and get AI analysis response"""

    # Get or create session
    session_id = req.session_id
    if not session_id:
        session = ChatSession(
            id=str(uuid.uuid4()),
            title=req.message[:50] + "..." if len(req.message) > 50 else req.message,
            dataset_id=req.dataset_id,
            user_id=current_user["sub"],
        )
        db.add(session)
        db.commit()
        session_id = session.id
    else:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    db.commit()

    # Get dataset
    dataset_id = req.dataset_id or (session.dataset_id if session else None)
    df = None
    dataset_name = "Dataset"

    if dataset_id:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.owner_id == current_user["sub"]).first()
        if dataset:
            try:
                df = load_dataset(dataset.file_path, dataset.file_type)
                dataset_name = dataset.name
            except Exception as e:
                logger.error(f"Failed to load dataset: {e}")

    # Generate AI response — try RAG first, fallback to agent
    if df is not None:
        # Build RAG index if not yet indexed — pgvector preferred, numpy fallback
        try:
            _rag.ensure_index(df, dataset_id, dataset_name, db_session=db)
        except Exception as e:
            logger.debug(f"RAG index build skipped: {e}")

        # Get chat history for context
        try:
            history_msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(6)
                .all()
            )
            chat_history = [{"role": m.role, "content": m.content} for m in reversed(history_msgs)]
        except Exception:
            chat_history = []

        # Attempt RAG answer
        rag_result = None
        try:
            rag_result = _rag.answer(
                req.message, dataset_id, df=df,
                dataset_name=dataset_name, chat_history=chat_history,
                db_session=db,
            )
        except Exception as e:
            logger.debug(f"RAG answer failed, falling back to agent: {e}")

        if rag_result and rag_result.get("confidence") in ("high", "medium"):
            # Use RAG answer — still run agent for charts and code
            agent_result = agent.analyze_question(req.message, df, dataset_name, history=chat_history)
            answer = rag_result["answer"]
            charts = agent_result.get("charts", [])
            code = agent_result.get("code")
            insights = agent_result.get("insights", [])
        else:
            # Fallback to full agent analysis
            result = agent.analyze_question(req.message, df, dataset_name, history=chat_history)
            answer = result.get("answer", "Analysis complete.")
            charts = result.get("charts", [])
            code = result.get("code")
            insights = result.get("insights", [])
    else:
        # No dataset — use LLM for general conversation (supports Arabic + any topic)
        lang = _detect_language(req.message)
        system = _build_system_prompt(has_dataset=False, lang=lang)
        try:
            answer = await asyncio.to_thread(
                llm_router.complete, system, req.message, 1000, "chat"
            )
        except Exception as e:
            logger.error(f"LLM general chat failed: {e}")
            answer = (
                "مرحباً! أنا DataMind، مساعدك الذكي لتحليل البيانات. كيف يمكنني مساعدتك؟"
                if _detect_language(req.message) == "arabic"
                else "Hello! I'm DataMind, your AI data analyst assistant. How can I help you?"
            )
        charts = []
        code = None
        insights = []

    # Save assistant message
    assistant_msg = ChatMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="assistant",
        content=answer,
        charts=charts,
        code=code,
        insights=insights,
    )
    db.add(assistant_msg)
    db.commit()

    return {
        "session_id": session_id,
        "message_id": assistant_msg.id,
        "role": "assistant",
        "content": answer,
        "charts": charts,
        "code": code,
        "insights": insights,
        "model": llm_router.last_model_used or "Unknown",
    }


@router.post("/stream")
async def stream_message(
    req: ChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream AI response tokens via Server-Sent Events (SSE).
    The frontend reads the stream and renders tokens progressively.
    """
    # Resolve dataset context
    dataset_id = req.dataset_id
    dataset_context = ""

    if dataset_id:
        dataset = db.query(Dataset).filter(
            Dataset.id == dataset_id,
            Dataset.owner_id == current_user["sub"],
        ).first()
        if dataset:
            try:
                df = load_dataset(dataset.file_path, dataset.file_type)
                cols = list(df.columns)[:20]
                dataset_context = (
                    f"Dataset: {dataset.name}\n"
                    f"Rows: {len(df)}, Columns: {len(df.columns)}\n"
                    f"Column names: {', '.join(cols)}"
                )
            except Exception:
                pass

    lang = _detect_language(req.message)
    system = _build_system_prompt(has_dataset=bool(dataset_context), lang=lang)
    if dataset_context:
        system += f"\n\nDataset context:\n{dataset_context}"

    async def event_generator():
        try:
            async for token in llm_router.stream_complete(system, req.message, max_tokens=800, task_type="chat"):
                payload = json.dumps({"token": token})
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user["sub"]).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}


# ─── Phase 17: Thread-to-Dashboard ────────────────────────────

@router.post("/sessions/{session_id}/convert-to-dashboard")
async def convert_session_to_dashboard(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Convert an AI chat session into a new dashboard — Hex AI Threads style.
    Extracts charts from messages and builds a dashboard layout automatically.
    """
    uid = current_user.get("sub") or current_user.get("id")
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == uid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id,
        ChatMessage.role == "assistant",
    ).all()

    # Collect charts from messages
    charts = []
    for msg in messages:
        if msg.charts:
            msg_charts = msg.charts if isinstance(msg.charts, list) else [msg.charts]
            for chart in msg_charts:
                charts.append({
                    "type": "plotly",
                    "title": f"Chart from: {msg.content[:50]}…",
                    "data": chart,
                })

    if not charts:
        raise HTTPException(
            status_code=400,
            detail="No charts found in this conversation. Ask questions that generate visualizations first.",
        )

    # Build dashboard layout (grid: 2 columns)
    layout = []
    for i, chart in enumerate(charts[:8]):
        layout.append({
            "i": str(i),
            "x": (i % 2) * 6,
            "y": (i // 2) * 4,
            "w": 6,
            "h": 4,
        })

    # Create the dashboard
    from models.database import Dashboard
    import uuid as _uuid
    dashboard = Dashboard(
        title=f"Dashboard from: {session.title or 'Chat Session'}",
        description=f"Auto-generated from chat session {session_id}",
        layout=layout,
        charts=charts,
        dataset_id=session.dataset_id,
        user_id=uid,
    )
    db.add(dashboard)
    db.commit()
    db.refresh(dashboard)

    return {
        "dashboard_id": dashboard.id,
        "title": dashboard.title,
        "charts_count": len(charts),
        "redirect_url": f"/dashboards/{dashboard.id}",
        "message": f"Created dashboard with {len(charts)} charts from your conversation.",
    }
