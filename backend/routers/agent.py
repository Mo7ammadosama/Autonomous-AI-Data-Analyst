"""
Agent Router — endpoints for the autonomous ReAct data analyst.

POST  /api/agent/run              → start a new agent run (async, returns run_id)
GET   /api/agent/runs             → list user's runs
GET   /api/agent/runs/{run_id}    → get run details + steps
GET   /api/agent/runs/{run_id}/stream → SSE real-time step stream
DELETE /api/agent/runs/{run_id}   → delete a run
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.database import AgentMemory, AgentRun, Dataset, get_db
from security.auth import get_current_user, verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["Autonomous Agent"])


# ─────────────────────────────────────────────────────────────────────────────
#  Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    task: str = Field(..., min_length=5, max_length=2000, description="Natural-language analysis task")
    dataset_id: Optional[str] = None
    connection_id: Optional[str] = None
    domain: Optional[str] = None


class AgentStepOut(BaseModel):
    iteration: int
    thought: str
    action: str
    action_input: dict
    observation: str
    figures: list[str] = []
    error: bool = False


class AgentRunOut(BaseModel):
    id: str
    task: str
    dataset_id: Optional[str]
    connection_id: Optional[str]
    domain: Optional[str]
    status: str
    steps: list[AgentStepOut]
    result_summary: Optional[str]
    charts: list[dict]
    token_usage: int
    duration_seconds: Optional[float]
    created_at: str


class AgentRunListItem(BaseModel):
    id: str
    task: str
    status: str
    domain: Optional[str]
    token_usage: int
    duration_seconds: Optional[float]
    created_at: str


class AgentRunStartResponse(BaseModel):
    run_id: str
    status: str
    message: str


# ─────────────────────────────────────────────────────────────────────────────
#  Background runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_agent_background(run_id: str, task: str, dataset_id, connection_id, domain, user_id: str):
    """Execute the agent in a background thread with its own DB session."""
    from models.database import SessionLocal
    from services.agent_executor import DataAnalystAgent

    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return

        agent = DataAnalystAgent()
        result = agent.run(
            task=task,
            run_id=run_id,
            db=db,
            user_id=user_id,
            dataset_id=dataset_id,
            db_connection_id=connection_id,
            domain=domain,
        )

        run.status = result.status
        run.steps = [
            {
                "iteration": s.iteration,
                "thought": s.thought,
                "action": s.action,
                "action_input": s.action_input,
                "observation": s.observation,
                "figures": s.figures,
                "error": s.error,
            }
            for s in result.steps
        ]
        run.result_summary = result.summary
        run.charts = result.charts
        run.token_usage = result.token_usage
        run.duration_seconds = result.duration_seconds
        db.commit()
        logger.info(f"Agent run {run_id} finished: {result.status}")

    except Exception as exc:
        logger.error(f"Agent run {run_id} crashed: {exc}", exc_info=True)
        try:
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.status = "failed"
                run.result_summary = f"Internal error: {exc}"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Routes — specific BEFORE parameterized
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run", response_model=AgentRunStartResponse)
def start_agent_run(
    req: AgentRunRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Start an autonomous agent run. Returns run_id immediately; execution is async."""
    run_id = str(uuid.uuid4())

    # Validate dataset if provided
    if req.dataset_id:
        ds = db.query(Dataset).filter(Dataset.id == req.dataset_id).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")

    # Persist run record
    run = AgentRun(
        id=run_id,
        user_id=current_user["sub"],
        task=req.task,
        dataset_id=req.dataset_id,
        connection_id=req.connection_id,
        domain=req.domain,
        status="running",
        steps=[],
        charts=[],
        token_usage=0,
    )
    db.add(run)
    db.commit()

    # Launch in background thread
    t = threading.Thread(
        target=_run_agent_background,
        args=(run_id, req.task, req.dataset_id, req.connection_id, req.domain, current_user["sub"]),
        daemon=True,
    )
    t.start()

    return AgentRunStartResponse(
        run_id=run_id,
        status="running",
        message="Agent started. Poll GET /api/agent/runs/{run_id} or stream SSE.",
    )


@router.get("/runs", response_model=list[AgentRunListItem])
def list_agent_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List the current user's agent runs, newest first."""
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.user_id == current_user["sub"])
        .order_by(AgentRun.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        AgentRunListItem(
            id=r.id,
            task=r.task,
            status=r.status,
            domain=r.domain,
            token_usage=r.token_usage or 0,
            duration_seconds=r.duration_seconds,
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}/stream")
def stream_agent_run(
    run_id: str,
    token: Optional[str] = Query(None, description="Bearer token — required because EventSource can't send headers"),
    db: Session = Depends(get_db),
):
    """SSE endpoint — streams steps as they are persisted to the DB.

    Authentication: pass ?token=<access_token> because the browser EventSource
    API cannot set custom headers (Authorization: Bearer is not supported).
    """
    # Authenticate via query-param token (EventSource workaround)
    if not token:
        raise HTTPException(status_code=401, detail="token query parameter required for SSE")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id: str = payload.get("sub", "")

    run = db.query(AgentRun).filter(
        AgentRun.id == run_id,
        AgentRun.user_id == user_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    from models.database import SessionLocal

    async def event_generator():
        last_step_count = 0
        polls = 0
        max_polls = 600        # 600 × 1s = 10 min ceiling
        ping_every = 3         # send keepalive ping every N polls

        # Emit an init step immediately so the UI shows activity right away
        yield f"data: {json.dumps({'type': 'step', 'step': {'iteration': 0, 'thought': 'Agent initialising...', 'action': 'init', 'action_input': {}, 'observation': '', 'figures': [], 'error': False}})}\n\n"

        # If run already finished when client connects, flush everything immediately
        initial_db = SessionLocal()
        try:
            r = initial_db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if r and r.status in ("completed", "failed"):
                for step in (r.steps or []):
                    yield f"data: {json.dumps({'type': 'step', 'step': step})}\n\n"
                final = json.dumps({
                    "type": "done",
                    "status": r.status,
                    "summary": r.result_summary or "",
                    "charts": r.charts or [],
                    "token_usage": r.token_usage or 0,
                    "duration_seconds": r.duration_seconds,
                    "error": r.result_summary if r.status == "failed" else None,
                })
                yield f"data: {final}\n\n"
                return
            last_step_count = len(r.steps or []) if r else 0
        finally:
            initial_db.close()

        while polls < max_polls:
            # Keepalive ping so the browser doesn't drop the connection
            if polls % ping_every == 0:
                yield "event: ping\ndata: {}\n\n"

            poll_db = SessionLocal()
            try:
                r = poll_db.query(AgentRun).filter(AgentRun.id == run_id).first()
                if not r:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Run not found'})}\n\n"
                    return

                steps = r.steps or []
                if len(steps) > last_step_count:
                    for step in steps[last_step_count:]:
                        yield f"data: {json.dumps({'type': 'step', 'step': step})}\n\n"
                    last_step_count = len(steps)

                if r.status in ("completed", "failed"):
                    final = json.dumps({
                        "type": "done",
                        "status": r.status,
                        "summary": r.result_summary or "",
                        "charts": r.charts or [],
                        "token_usage": r.token_usage or 0,
                        "duration_seconds": r.duration_seconds,
                        "error": r.result_summary if r.status == "failed" else None,
                    })
                    yield f"data: {final}\n\n"
                    return
            except Exception as exc:
                logger.error(f"SSE poll error for run {run_id}: {exc}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                return
            finally:
                poll_db.close()

            await asyncio.sleep(1)
            polls += 1

        yield f"data: {json.dumps({'type': 'timeout', 'message': 'Stream timed out after 10 minutes'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
            "Connection": "keep-alive",
        },
    )


@router.get("/runs/{run_id}/pdf")
def download_run_pdf(
    run_id: str,
    token: Optional[str] = Query(None, description="Auth token — for browser download links (same as SSE)"),
    db: Session = Depends(get_db),
):
    """Generate and return a PDF report for a completed agent run.

    Authentication: pass ?token=<access_token> for browser download links
    (same approach as the SSE endpoint — EventSource/anchor tags can't set headers).
    """
    import io
    import json as _json
    import tempfile
    from datetime import datetime as _dt
    from fastapi.responses import Response

    if not token:
        raise HTTPException(status_code=401, detail="token query parameter required for PDF download")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id: str = payload.get("sub", "")

    run = db.query(AgentRun).filter(
        AgentRun.id == run_id,
        AgentRun.user_id == user_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, PageBreak,
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        # Custom styles
        title_style = ParagraphStyle(
            "CoverTitle",
            parent=styles["Title"],
            fontSize=28,
            textColor=colors.HexColor("#4F46E5"),
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=13,
            textColor=colors.HexColor("#6B7280"),
            spaceAfter=4,
            alignment=TA_CENTER,
        )
        h1_style = ParagraphStyle(
            "H1",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=18,
            spaceAfter=8,
        )
        h2_style = ParagraphStyle(
            "H2",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=colors.HexColor("#374151"),
            spaceBefore=12,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#374151"),
            spaceAfter=4,
            leading=14,
        )
        finding_style = ParagraphStyle(
            "Finding",
            parent=body_style,
            leftIndent=12,
            bulletIndent=0,
        )

        story = []

        # ── Cover page ──────────────────────────────────────────────────────
        story.append(Spacer(1, 3 * cm))
        story.append(Paragraph("DataMind AI", title_style))
        story.append(Paragraph("Analysis Report", subtitle_style))
        story.append(Spacer(1, 0.5 * cm))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#4F46E5")))
        story.append(Spacer(1, 0.5 * cm))

        task_text = run.task or "Untitled Analysis"
        story.append(Paragraph(task_text, ParagraphStyle(
            "TaskTitle",
            parent=styles["Normal"],
            fontSize=14,
            textColor=colors.HexColor("#111827"),
            spaceAfter=12,
            alignment=TA_CENTER,
        )))

        generated_at = _dt.now().strftime("%B %d, %Y at %H:%M")
        story.append(Paragraph(f"Generated: {generated_at}", subtitle_style))
        story.append(Paragraph(f"Status: {run.status.upper()}", subtitle_style))
        if run.duration_seconds:
            story.append(Paragraph(f"Duration: {run.duration_seconds:.1f}s", subtitle_style))
        story.append(PageBreak())

        # ── Try to parse structured JSON result ─────────────────────────────
        structured: dict | None = None
        summary_text = run.result_summary or ""
        try:
            candidate = _json.loads(summary_text)
            if isinstance(candidate, dict) and "executive_summary" in candidate:
                structured = candidate
        except (_json.JSONDecodeError, TypeError):
            pass

        if structured:
            # Executive Summary
            story.append(Paragraph("Executive Summary", h1_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
            story.append(Spacer(1, 0.3 * cm))
            exec_text = structured.get("executive_summary", "")
            story.append(Paragraph(exec_text, ParagraphStyle(
                "ExecSummary",
                parent=body_style,
                fontSize=11,
                textColor=colors.HexColor("#1F2937"),
                backColor=colors.HexColor("#EEF2FF"),
                borderPadding=(8, 8, 8, 8),
                leading=16,
            )))
            story.append(Spacer(1, 0.4 * cm))

            # Confidence + Data Quality
            confidence = structured.get("confidence", "")
            dq_notes = structured.get("data_quality_notes", "")
            if confidence or dq_notes:
                meta_rows = []
                if confidence:
                    meta_rows.append(["Confidence Level", confidence.upper()])
                if dq_notes:
                    meta_rows.append(["Data Quality Notes", dq_notes])
                if meta_rows:
                    meta_table = Table(meta_rows, colWidths=[4 * cm, 13 * cm])
                    meta_table.setStyle(TableStyle([
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6B7280")),
                        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ]))
                    story.append(meta_table)
                    story.append(Spacer(1, 0.4 * cm))

            # Key Findings
            key_findings = structured.get("key_findings", [])
            if key_findings:
                story.append(Paragraph("Key Findings", h1_style))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
                story.append(Spacer(1, 0.2 * cm))
                for idx, finding in enumerate(key_findings, 1):
                    story.append(Paragraph(f"{idx}.&nbsp;&nbsp;{finding}", finding_style))
                story.append(Spacer(1, 0.4 * cm))

            # Root Causes
            root_causes = structured.get("root_causes", [])
            if root_causes:
                story.append(Paragraph("Root Causes", h1_style))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
                story.append(Spacer(1, 0.2 * cm))
                for cause in root_causes:
                    story.append(Paragraph(f"• {cause}", finding_style))
                story.append(Spacer(1, 0.4 * cm))

            # Recommendations table
            recommendations = structured.get("recommendations", [])
            if recommendations:
                story.append(Paragraph("Recommendations", h1_style))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
                story.append(Spacer(1, 0.3 * cm))

                table_data = [["Priority", "Action", "Expected Impact"]]
                for rec in recommendations:
                    if isinstance(rec, dict):
                        priority = str(rec.get("priority", "")).upper()
                        action_txt = str(rec.get("action", ""))
                        impact = str(rec.get("expected_impact", ""))
                    else:
                        priority, action_txt, impact = "", str(rec), ""
                    table_data.append([priority, action_txt, impact])

                rec_table = Table(
                    table_data,
                    colWidths=[2.5 * cm, 9 * cm, 6 * cm],
                )
                priority_colors = {"HIGH": colors.HexColor("#FEE2E2"), "MEDIUM": colors.HexColor("#FEF9C3"), "LOW": colors.HexColor("#DCFCE7")}
                table_style_cmds = [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
                for row_idx, rec in enumerate(recommendations, 1):
                    if isinstance(rec, dict):
                        p = str(rec.get("priority", "")).upper()
                        if p in priority_colors:
                            table_style_cmds.append(
                                ("BACKGROUND", (0, row_idx), (0, row_idx), priority_colors[p])
                            )
                rec_table.setStyle(TableStyle(table_style_cmds))
                story.append(rec_table)
                story.append(Spacer(1, 0.4 * cm))

            # Risks
            risks = structured.get("risks", [])
            if risks:
                story.append(Paragraph("Risks", h1_style))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
                story.append(Spacer(1, 0.2 * cm))
                for risk in risks:
                    story.append(Paragraph(f"⚠ {risk}", ParagraphStyle(
                        "Risk",
                        parent=finding_style,
                        textColor=colors.HexColor("#991B1B"),
                    )))
                story.append(Spacer(1, 0.4 * cm))

        else:
            # Fallback: render the plain markdown summary as paragraphs
            story.append(Paragraph("Analysis Report", h1_style))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
            story.append(Spacer(1, 0.3 * cm))
            for line in summary_text.split("\n"):
                line = line.strip()
                if not line:
                    story.append(Spacer(1, 0.2 * cm))
                elif line.startswith("## "):
                    story.append(Paragraph(line[3:], h2_style))
                elif line.startswith("# "):
                    story.append(Paragraph(line[2:], h1_style))
                else:
                    story.append(Paragraph(line, body_style))

        # ── Footer note ─────────────────────────────────────────────────────
        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
        story.append(Paragraph(
            "Generated by DataMind AI Analytics Platform — Confidential",
            ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.HexColor("#9CA3AF"), alignment=TA_CENTER),
        ))

        doc.build(story)
        pdf_bytes = buf.getvalue()

        safe_task = re.sub(r"[^a-zA-Z0-9_-]", "_", (run.task or "report")[:40])
        filename = f"datamind_report_{safe_task}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="ReportLab is not installed. Run: pip install reportlab",
        )
    except Exception as exc:
        logger.error(f"PDF generation failed for run {run_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get full details of a single agent run including all steps."""
    run = db.query(AgentRun).filter(
        AgentRun.id == run_id,
        AgentRun.user_id == current_user["sub"],
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps_out = [
        AgentStepOut(
            iteration=s.get("iteration", 0),
            thought=s.get("thought", ""),
            action=s.get("action", ""),
            action_input=s.get("action_input", {}),
            observation=s.get("observation", ""),
            figures=s.get("figures", []),
            error=s.get("error", False),
        )
        for s in (run.steps or [])
    ]

    return AgentRunOut(
        id=run.id,
        task=run.task,
        dataset_id=run.dataset_id,
        connection_id=run.connection_id,
        domain=run.domain,
        status=run.status,
        steps=steps_out,
        result_summary=run.result_summary,
        charts=run.charts or [],
        token_usage=run.token_usage or 0,
        duration_seconds=run.duration_seconds,
        created_at=run.created_at.isoformat(),
    )


@router.delete("/runs/{run_id}")
def delete_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an agent run."""
    run = db.query(AgentRun).filter(
        AgentRun.id == run_id,
        AgentRun.user_id == current_user["sub"],
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(run)
    db.commit()
    return {"message": "Run deleted"}


# ─────────────────────────────────────────────────────────────────────────────
#  Memory endpoints
# ─────────────────────────────────────────────────────────────────────────────

class MemoryOut(BaseModel):
    id: str
    memory_type: str
    key: str
    value: str
    importance: float
    access_count: int
    source_run_id: Optional[str]
    created_at: str


class CorrectionRequest(BaseModel):
    correction: str = Field(..., min_length=5, max_length=1000)
    run_id: Optional[str] = None


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all memories for the current user, ordered by importance."""
    memories = (
        db.query(AgentMemory)
        .filter(AgentMemory.user_id == current_user["sub"])
        .order_by(AgentMemory.importance.desc(), AgentMemory.access_count.desc())
        .all()
    )
    return [
        MemoryOut(
            id=m.id,
            memory_type=m.memory_type,
            key=m.key,
            value=m.value,
            importance=m.importance,
            access_count=m.access_count or 0,
            source_run_id=m.source_run_id,
            created_at=m.created_at.isoformat(),
        )
        for m in memories
    ]


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a specific memory."""
    mem = db.query(AgentMemory).filter(
        AgentMemory.id == memory_id,
        AgentMemory.user_id == current_user["sub"],
    ).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(mem)
    db.commit()
    return {"message": "Memory deleted"}


@router.post("/memories/correction")
def save_correction(
    req: CorrectionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Save a user correction as a high-importance memory."""
    from services.agent_memory import AgentMemoryService
    AgentMemoryService.save_correction(
        db=db,
        user_id=current_user["sub"],
        run_id=req.run_id,
        correction_text=req.correction,
    )
    return {"message": "Correction saved"}
