"""
Reports router - generates comprehensive analysis reports including pipeline data
"""

from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import logging
import io
import json
import re

from models.database import get_db, Dataset, PipelineResult
from services.data_processor import load_dataset, profile_dataset, compute_descriptive_stats
from services.visualization import generate_auto_charts
from services.ai_agent import AIDataAnalystAgent
from security.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
agent = AIDataAnalystAgent()


class ReportRequest(BaseModel):
    dataset_id: str
    title: Optional[str] = None
    include_charts: bool = True
    include_insights: bool = True
    include_stats: bool = True
    include_pipeline: bool = True   # include story / recommendations / anomalies


def _strip_markdown(text: str) -> str:
    """Strip markdown syntax for plain-text PDF paragraphs."""
    if not text:
        return ""
    text = re.sub(r"#+\s*", "", text)          # headings
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)      # italic
    text = re.sub(r"`(.*?)`", r"\1", text)        # inline code
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)  # links
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)  # bullets
    return text.strip()


@router.post("/generate-pdf")
async def generate_pdf_report(
    req: ReportRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dataset = db.query(Dataset).filter(
        Dataset.id == req.dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, KeepTogether
        )
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

        df = load_dataset(dataset.file_path, dataset.file_type)
        profile = profile_dataset(df)
        stats = compute_descriptive_stats(df)
        insights = agent.generate_insights(df, dataset.name)

        # Load pipeline result if available
        pipeline = None
        if req.include_pipeline:
            pipeline = db.query(PipelineResult).filter(
                PipelineResult.dataset_id == req.dataset_id,
                PipelineResult.status == "done",
            ).first()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=0.9 * inch, leftMargin=0.9 * inch,
            topMargin=1 * inch, bottomMargin=0.9 * inch,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        INDIGO  = colors.HexColor("#6366f1")
        VIOLET  = colors.HexColor("#8b5cf6")
        SLATE   = colors.HexColor("#334155")
        SLATE_L = colors.HexColor("#64748b")
        BG_LIGHT = colors.HexColor("#f8fafc")
        EMERALD = colors.HexColor("#10b981")
        RED     = colors.HexColor("#ef4444")
        AMBER   = colors.HexColor("#f59e0b")

        title_style = ParagraphStyle(
            "ReportTitle", parent=styles["Heading1"],
            fontSize=26, spaceAfter=4, textColor=INDIGO, alignment=TA_CENTER, leading=30,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle", parent=styles["Normal"],
            fontSize=11, spaceAfter=20, textColor=SLATE_L, alignment=TA_CENTER,
        )
        h2_style = ParagraphStyle(
            "H2", parent=styles["Heading2"],
            fontSize=14, spaceBefore=16, spaceAfter=8, textColor=INDIGO,
        )
        h3_style = ParagraphStyle(
            "H3", parent=styles["Heading3"],
            fontSize=11, spaceBefore=10, spaceAfter=6, textColor=VIOLET,
        )
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"],
            fontSize=9.5, spaceAfter=5, textColor=SLATE, leading=14,
        )
        bullet_style = ParagraphStyle(
            "Bullet", parent=styles["Normal"],
            fontSize=9.5, spaceAfter=3, textColor=SLATE, leading=14,
            leftIndent=14, firstLineIndent=-10,
        )
        caption_style = ParagraphStyle(
            "Caption", parent=styles["Normal"],
            fontSize=8, textColor=SLATE_L, spaceAfter=8,
        )

        def hr():
            return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=10, spaceBefore=4)

        def section_table(data, col_widths, header_color=INDIGO):
            t = Table(data, colWidths=col_widths)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), header_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            return t

        elements = []

        # ── Title ─────────────────────────────────────────────────────────
        title = req.title or f"{dataset.name} — Analysis Report"
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph(title, title_style))
        elements.append(Paragraph(
            f"Generated by DataMind AI  •  Dataset: {dataset.name}  •  "
            f"{profile['shape']['rows']:,} rows × {profile['shape']['columns']} columns",
            subtitle_style,
        ))
        elements.append(hr())

        # ── Dataset Overview ───────────────────────────────────────────────
        elements.append(Paragraph("1. Dataset Overview", h2_style))
        overview_data = [
            ["Property", "Value"],
            ["Dataset Name",   dataset.name],
            ["Total Rows",     f"{profile['shape']['rows']:,}"],
            ["Total Columns",  str(profile["shape"]["columns"])],
            ["Duplicate Rows", str(profile["duplicates"])],
            ["File Type",      dataset.file_type.upper()],
            ["File Size",      f"{(dataset.file_size or 0) / 1024:.1f} KB"],
        ]
        elements.append(section_table(overview_data, [2.5 * inch, 4.3 * inch]))
        elements.append(Spacer(1, 12))

        # Missing data summary
        missing = profile.get("missing_summary", {})
        if missing:
            elements.append(Paragraph("Missing Values by Column", h3_style))
            missing_data = [["Column", "Missing Count", "Missing %"]]
            for col, info in list(missing.items())[:12]:
                missing_data.append([col, str(info.get("count", 0)), f"{info.get('pct', 0)}%"])
            elements.append(section_table(missing_data, [3 * inch, 1.8 * inch, 1.9 * inch], VIOLET))
            elements.append(Spacer(1, 8))

        # ── Column Profile ─────────────────────────────────────────────────
        elements.append(Paragraph("2. Column Profile", h2_style))
        col_data = [["Column", "Data Type", "Semantic Type", "Unique Values", "Missing %"]]
        for col, info in list(profile["columns"].items())[:20]:
            col_data.append([
                col,
                str(info.get("dtype", "–")),
                str(info.get("semantic_type", "–")),
                str(info.get("unique_count", "–")),
                f"{info.get('missing_pct', 0)}%",
            ])
        elements.append(section_table(
            col_data,
            [2.0 * inch, 1.2 * inch, 1.3 * inch, 1.2 * inch, 1.0 * inch],
        ))
        elements.append(Spacer(1, 12))

        # ── Descriptive Statistics ─────────────────────────────────────────
        if stats and stats.get("numeric"):
            elements.append(Paragraph("3. Descriptive Statistics", h2_style))
            stat_cols = ["Column", "Mean", "Std Dev", "Min", "Median", "Max"]
            stat_data = [stat_cols]
            for col, s in list(stats["numeric"].items())[:12]:
                stat_data.append([
                    col,
                    f"{s.get('mean', 0):.2f}",
                    f"{s.get('std', 0):.2f}",
                    f"{s.get('min', 0):.2f}",
                    f"{s.get('50%', 0):.2f}",
                    f"{s.get('max', 0):.2f}",
                ])
            elements.append(section_table(
                stat_data,
                [2.2 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch],
            ))
            elements.append(Spacer(1, 12))

        # ── AI Pipeline: Data Story ────────────────────────────────────────
        if pipeline and pipeline.story:
            elements.append(Paragraph("4. AI Data Story", h2_style))
            elements.append(Paragraph(
                "The following narrative was automatically generated by the DataMind AI analysis pipeline:",
                caption_style,
            ))
            story_lines = _strip_markdown(pipeline.story).split("\n")
            for line in story_lines:
                line = line.strip()
                if not line:
                    elements.append(Spacer(1, 4))
                    continue
                if line.startswith("•"):
                    elements.append(Paragraph(line, bullet_style))
                else:
                    elements.append(Paragraph(line, body_style))
            elements.append(Spacer(1, 10))

        # ── Pipeline Insights ──────────────────────────────────────────────
        pipeline_insights = (pipeline.insights or []) if pipeline else []
        if pipeline_insights:
            section_num = 5
            elements.append(Paragraph(f"{section_num}. AI Pipeline Insights", h2_style))
            sev_colors = {"high": RED, "medium": AMBER, "low": EMERALD, "info": INDIGO}
            ins_data = [["Severity", "Title", "Detail"]]
            for ins in pipeline_insights[:10]:
                ins_data.append([
                    ins.get("severity", "info").upper(),
                    ins.get("title", ""),
                    ins.get("content", "")[:120] + ("…" if len(ins.get("content", "")) > 120 else ""),
                ])
            t = Table(ins_data, colWidths=[0.9 * inch, 2.0 * inch, 3.8 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), INDIGO),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (2, 1), (2, -1), True),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 12))
            section_num = 6
        else:
            section_num = 5

        # ── Business Recommendations ───────────────────────────────────────
        pipeline_recs = (pipeline.recommendations or []) if pipeline else []
        if pipeline_recs:
            elements.append(Paragraph(f"{section_num}. Business Recommendations", h2_style))
            priority_order = {"high": 0, "medium": 1, "low": 2}
            sorted_recs = sorted(pipeline_recs, key=lambda r: priority_order.get(r.get("priority", "low"), 2))
            for rec in sorted_recs[:8]:
                priority = rec.get("priority", "low").upper()
                p_color = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#10b981"}.get(priority, "#6366f1")
                elements.append(KeepTogether([
                    Paragraph(
                        f'<font color="{p_color}"><b>[{priority}]</b></font> {rec.get("title", "")}',
                        h3_style,
                    ),
                    Paragraph(rec.get("description", ""), body_style),
                    Paragraph(f"→ Action: {rec.get('ai_action') or rec.get('action', '')}", bullet_style),
                    Spacer(1, 4),
                ]))
            elements.append(Spacer(1, 8))
            section_num += 1

        # ── Anomaly Alerts ─────────────────────────────────────────────────
        if pipeline and pipeline.anomalies:
            alerts = pipeline.anomalies.get("summary_alerts", [])
            if alerts:
                elements.append(Paragraph(f"{section_num}. Anomaly Detection", h2_style))
                for alert in alerts[:10]:
                    elements.append(Paragraph(f"⚠  {alert}", bullet_style))
                elements.append(Spacer(1, 10))
                section_num += 1

        # ── Quick Insights (from AI agent) ────────────────────────────────
        if insights:
            elements.append(Paragraph(f"{section_num}. Quick AI Insights", h2_style))
            for ins in insights[:8]:
                elements.append(Paragraph(
                    f"• <b>{ins.get('title', '')}</b>: {ins.get('content', '')}",
                    bullet_style,
                ))
            elements.append(Spacer(1, 8))

        doc.build(elements)
        buffer.seek(0)
        return Response(
            content=buffer.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{dataset.name}_report.pdf"'},
        )

    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab not installed. Run: pip install reportlab")
    except Exception as e:
        logger.error(f"PDF generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{dataset_id}")
async def get_report_summary(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.owner_id == current_user["sub"],
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        profile = profile_dataset(df)
        stats = compute_descriptive_stats(df)
        insights = agent.generate_insights(df, dataset.name)
        charts = generate_auto_charts(df, max_charts=4)
        return {
            "dataset": {
                "name": dataset.name,
                "rows": profile["shape"]["rows"],
                "columns": profile["shape"]["columns"],
            },
            "profile": profile,
            "stats": stats,
            "insights": insights,
            "charts": charts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
