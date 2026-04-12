"""
ReportBuilder — assembles structured reports from typed sections.
Supports export to PDF (ReportLab), HTML, and JSON.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

SectionType = Literal["text", "chart", "table", "metric_card", "insight_list"]


@dataclass
class ReportSection:
    id: str
    type: SectionType
    title: str
    content: Any          # type-specific payload
    order: int = 0        # supports drag-and-drop reordering


@dataclass
class BuiltReport:
    name: str
    domain: Optional[str]
    sections: list[ReportSection]
    metadata: dict = field(default_factory=dict)


class ReportBuilder:
    """
    Assemble a report from ordered sections and export it.

    Section content shapes:
      text        → {"body": "markdown string"}
      chart       → {"base64": "...", "caption": "..."}
      table       → {"html": "<table>...</table>", "caption": "..."}
      metric_card → {"metrics": [{"label": "...", "value": "...", "delta": "..."}]}
      insight_list→ {"insights": ["...", "..."]}
    """

    def __init__(self, report: BuiltReport):
        self.report = report
        # Sort sections by order field
        self.report.sections.sort(key=lambda s: s.order)

    # ------------------------------------------------------------------ #
    #  JSON export                                                         #
    # ------------------------------------------------------------------ #

    def to_json(self) -> str:
        data = {
            "name": self.report.name,
            "domain": self.report.domain,
            "metadata": self.report.metadata,
            "sections": [
                {
                    "id": s.id,
                    "type": s.type,
                    "title": s.title,
                    "content": s.content,
                    "order": s.order,
                }
                for s in self.report.sections
            ],
        }
        return json.dumps(data, indent=2, default=str)

    # ------------------------------------------------------------------ #
    #  HTML export                                                         #
    # ------------------------------------------------------------------ #

    def to_html(self) -> str:
        parts = [
            "<!DOCTYPE html><html><head>",
            f"<title>{self.report.name}</title>",
            "<meta charset='utf-8'>",
            "<style>",
            "body{font-family:system-ui,sans-serif;max-width:900px;margin:40px auto;color:#1a1a2e;line-height:1.6}",
            "h1{font-size:2rem;border-bottom:2px solid #6366f1;padding-bottom:8px}",
            "h2{font-size:1.4rem;color:#6366f1;margin-top:2rem}",
            ".metric-card{display:inline-block;background:#f8f9ff;border:1px solid #e0e0ff;border-radius:12px;padding:12px 20px;margin:8px;text-align:center}",
            ".metric-value{font-size:1.8rem;font-weight:700;color:#6366f1}",
            ".metric-label{font-size:0.85rem;color:#666}",
            ".insight{background:#f0f4ff;border-left:3px solid #6366f1;padding:8px 12px;margin:6px 0;border-radius:4px}",
            "table{width:100%;border-collapse:collapse;margin:12px 0}",
            "th{background:#6366f1;color:#fff;padding:8px 12px;text-align:left}",
            "td{padding:8px 12px;border-bottom:1px solid #eee}",
            "img{max-width:100%;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.1)}",
            "</style></head><body>",
            f"<h1>{self.report.name}</h1>",
        ]

        if self.report.domain:
            parts.append(f"<p><em>Domain: {self.report.domain}</em></p>")

        for section in self.report.sections:
            parts.append(f"<h2>{section.title}</h2>")
            parts.append(self._render_section_html(section))

        parts.append("</body></html>")
        return "\n".join(parts)

    def _render_section_html(self, section: ReportSection) -> str:
        c = section.content or {}
        if section.type == "text":
            body = c.get("body", "")
            # Basic markdown-to-HTML (bold, italic, code)
            body = body.replace("**", "<strong>", 1)
            body = body.replace("**", "</strong>", 1)
            return f"<p>{body}</p>"

        elif section.type == "chart":
            b64 = c.get("base64", "")
            caption = c.get("caption", "")
            if b64:
                return f'<img src="data:image/png;base64,{b64}" alt="{caption}"><p><small>{caption}</small></p>'
            return f"<p>[Chart placeholder: {caption}]</p>"

        elif section.type == "table":
            return c.get("html", "<p>[Table]</p>") + f"<p><small>{c.get('caption','')}</small></p>"

        elif section.type == "metric_card":
            metrics = c.get("metrics", [])
            card_parts = []
            for m in metrics:
                delta_html = ""
                if m.get("delta"):
                    delta_html = '<div style="color:#10b981;font-size:.8rem">&#8593; ' + m["delta"] + "</div>"
                card_parts.append(
                    '<div class="metric-card">'
                    '<div class="metric-value">' + str(m.get("value", "")) + "</div>"
                    '<div class="metric-label">' + str(m.get("label", "")) + "</div>"
                    + delta_html + "</div>"
                )
            return '<div style="display:flex;flex-wrap:wrap">' + "".join(card_parts) + "</div>"

        elif section.type == "insight_list":
            insights = c.get("insights", [])
            items = "".join(f'<div class="insight">{ins}</div>' for ins in insights)
            return items

        return f"<p>[Section type '{section.type}' not rendered]</p>"

    # ------------------------------------------------------------------ #
    #  PDF export (ReportLab)                                              #
    # ------------------------------------------------------------------ #

    def to_pdf_bytes(self) -> bytes:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                Image as RLImage, HRFlowable,
            )
        except ImportError:
            raise RuntimeError("reportlab is not installed. pip install reportlab")

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )
        styles = getSampleStyleSheet()
        accent = colors.HexColor("#6366f1")

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            textColor=accent,
            fontSize=22,
            spaceAfter=12,
        )
        h2_style = ParagraphStyle(
            "H2", parent=styles["Heading2"],
            textColor=accent, fontSize=14, spaceBefore=16, spaceAfter=6,
        )
        body_style = styles["BodyText"]
        story = []

        story.append(Paragraph(self.report.name, title_style))
        if self.report.domain:
            story.append(Paragraph(f"Domain: {self.report.domain}", styles["Italic"]))
        story.append(HRFlowable(width="100%", thickness=1, color=accent))
        story.append(Spacer(1, 0.4*cm))

        for section in self.report.sections:
            story.append(Paragraph(section.title, h2_style))
            story.extend(self._render_section_pdf(section, body_style, styles))
            story.append(Spacer(1, 0.3*cm))

        doc.build(story)
        return buf.getvalue()

    def _render_section_pdf(self, section: ReportSection, body_style, styles) -> list:
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image as RLImage
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        c = section.content or {}
        flowables = []

        if section.type == "text":
            body = c.get("body", "")
            for para in body.split("\n\n"):
                if para.strip():
                    flowables.append(Paragraph(para.strip(), body_style))

        elif section.type == "chart":
            b64 = c.get("base64", "")
            if b64:
                try:
                    img_bytes = base64.b64decode(b64)
                    img_buf = io.BytesIO(img_bytes)
                    img = RLImage(img_buf, width=14*cm, height=8*cm)
                    flowables.append(img)
                    if c.get("caption"):
                        flowables.append(Paragraph(c["caption"], styles["Italic"]))
                except Exception as exc:
                    flowables.append(Paragraph(f"[Chart error: {exc}]", body_style))

        elif section.type == "table":
            # Try parsing simple HTML table into RL table
            rows = _html_table_to_rows(c.get("html", ""))
            if rows:
                tbl = Table(rows, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5ff")]),
                ]))
                flowables.append(tbl)

        elif section.type == "metric_card":
            metrics = c.get("metrics", [])
            if metrics:
                rows = [["Metric", "Value", "Change"]]
                for m in metrics:
                    rows.append([m.get("label", ""), m.get("value", ""), m.get("delta", "")])
                tbl = Table(rows, colWidths=[6*cm, 4*cm, 4*cm])
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ]))
                flowables.append(tbl)

        elif section.type == "insight_list":
            for insight in c.get("insights", []):
                flowables.append(Paragraph(f"• {insight}", body_style))

        return flowables or [Spacer(1, 0.2*cm)]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _html_table_to_rows(html: str) -> list[list[str]]:
    """Minimal HTML table parser for PDF rendering."""
    import re
    rows = []
    for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_match.group(1), re.DOTALL | re.IGNORECASE)
        rows.append([re.sub(r"<[^>]+>", "", c).strip() for c in cells])
    return rows


def build_report_from_agent_run(run) -> BuiltReport:
    """Convert an AgentRun DB record into a BuiltReport for export."""
    import uuid as _uuid

    sections: list[ReportSection] = []
    order = 0

    # Summary section
    if run.result_summary:
        sections.append(ReportSection(
            id=str(_uuid.uuid4()),
            type="text",
            title="Executive Summary",
            content={"body": run.result_summary},
            order=order,
        ))
        order += 1

    # Charts
    for chart in (run.charts or []):
        sections.append(ReportSection(
            id=str(_uuid.uuid4()),
            type="chart",
            title=chart.get("title", "Chart"),
            content={"base64": chart.get("base64", ""), "caption": chart.get("title", "")},
            order=order,
        ))
        order += 1

    return BuiltReport(
        name=f"Analysis Report — {run.task[:60]}",
        domain=run.domain,
        sections=sections,
        metadata={
            "run_id": run.id,
            "token_usage": run.token_usage,
            "duration_seconds": run.duration_seconds,
        },
    )
