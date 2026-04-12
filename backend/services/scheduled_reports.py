"""
Scheduled Reports Service — generate and email PDF reports on a schedule.

Integrates with the existing PDF report generation in routers/reports.py.
Uses aiosmtplib for async email delivery.
"""

import os
import io
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "reports@datamind.ai")

FREQUENCY_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def compute_next_run(frequency: str, from_dt: Optional[datetime] = None) -> datetime:
    base = from_dt or datetime.utcnow()
    days = FREQUENCY_DAYS.get(frequency, 7)
    return base + timedelta(days=days)


def _generate_pdf_bytes(dataset_id: str, title: str, db) -> bytes:
    """Generate a PDF report and return as bytes using the existing report logic."""
    from models.database import Dataset, PipelineResult
    from services.data_processor import load_dataset, profile_dataset, compute_descriptive_stats, compute_correlations
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise ValueError(f"Dataset {dataset_id} not found")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(title or f"Report: {dataset.name}", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    try:
        df = load_dataset(dataset.file_path, dataset.file_type)
        profile = profile_dataset(df)
        story.append(Paragraph("Dataset Overview", styles["Heading2"]))
        story.append(Paragraph(f"Rows: {profile['shape']['rows']:,}  |  Columns: {profile['shape']['columns']}", styles["Normal"]))
        story.append(Spacer(1, 8))

        stats = compute_descriptive_stats(df)
        story.append(Paragraph("Summary Statistics", styles["Heading2"]))
        for col, s in list(stats.items())[:10]:
            story.append(Paragraph(f"<b>{col}</b>: mean={s.get('mean','N/A'):.4g}, std={s.get('std','N/A'):.4g}, min={s.get('min','N/A'):.4g}, max={s.get('max','N/A'):.4g}", styles["Normal"]))
        story.append(Spacer(1, 8))
    except Exception as e:
        story.append(Paragraph(f"Could not load data: {e}", styles["Normal"]))

    # Pipeline insights
    pipeline = db.query(PipelineResult).filter(PipelineResult.dataset_id == dataset_id).first()
    if pipeline:
        if pipeline.story:
            story.append(Paragraph("Data Story", styles["Heading2"]))
            story.append(Paragraph(str(pipeline.story)[:800], styles["Normal"]))
            story.append(Spacer(1, 8))
        if pipeline.insights:
            story.append(Paragraph("Key Insights", styles["Heading2"]))
            for ins in (pipeline.insights or [])[:5]:
                if isinstance(ins, dict):
                    story.append(Paragraph(f"• {ins.get('title', '')}: {ins.get('content', '')}", styles["Normal"]))
            story.append(Spacer(1, 8))

    doc.build(story)
    buf.seek(0)
    return buf.read()


async def send_report_email(
    recipient: str,
    subject: str,
    body_html: str,
    pdf_bytes: bytes,
    pdf_filename: str = "report.pdf",
) -> bool:
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("SMTP not configured — scheduled report email skipped")
        return False
    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = recipient

        html_part = MIMEText(body_html, "html")
        msg.attach(html_part)

        pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(pdf_part)

        await aiosmtplib.send(
            msg, hostname=SMTP_HOST, port=SMTP_PORT,
            username=SMTP_USER, password=SMTP_PASSWORD,
            use_tls=False, start_tls=True,
        )
        logger.info(f"Scheduled report sent to {recipient}")
        return True
    except Exception as e:
        logger.error(f"Failed to send scheduled report: {e}")
        return False


def process_due_reports(db) -> int:
    """Find and send all scheduled reports that are due. Returns count sent."""
    from models.database import ScheduledReport
    now = datetime.utcnow()
    reports = db.query(ScheduledReport).filter(
        ScheduledReport.is_active == True,
        ScheduledReport.next_run <= now,
    ).all()

    sent = 0
    for report in reports:
        try:
            import asyncio
            pdf_bytes = _generate_pdf_bytes(report.dataset_id, report.title, db)
            subject = f"[DataMind] Scheduled Report: {report.title}"
            body_html = f"""
<html><body style="font-family:sans-serif;color:#1e293b">
<h2 style="color:#6366f1">📊 Your Scheduled Report is Ready</h2>
<p>Your <b>{report.frequency}</b> report "<b>{report.title}</b>" is attached as a PDF.</p>
<p style="color:#64748b;font-size:12px">Sent by DataMind AI Analytics Platform</p>
</body></html>"""
            filename = f"{report.title.replace(' ', '_')}_{now.strftime('%Y%m%d')}.pdf"
            asyncio.run(send_report_email(
                report.email_recipient, subject, body_html, pdf_bytes, filename
            ))
            report.last_sent = now
            report.next_run = compute_next_run(report.frequency, now)
            sent += 1
        except Exception as e:
            logger.error(f"Failed to process scheduled report {report.id}: {e}")

    db.commit()
    return sent
