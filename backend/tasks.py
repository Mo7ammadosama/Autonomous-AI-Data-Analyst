"""
Celery tasks — background workers for heavy computations.
"""

import logging
from celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.run_pipeline_task", bind=True, max_retries=2)
def run_pipeline_task(self, dataset_id: str):
    """Run the full auto-analysis pipeline for a dataset."""
    try:
        from models.database import SessionLocal
        from services.auto_pipeline import run_pipeline
        from services.llm_service import LLMService

        db = SessionLocal()
        llm = LLMService()
        try:
            run_pipeline(dataset_id, db, llm)
            logger.info(f"Pipeline completed for dataset {dataset_id}")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"Pipeline task failed for {dataset_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.run_autonomous_task", bind=True, max_retries=2)
def run_autonomous_task(self, dataset_id: str, owner_id: str):
    """Run the autonomous analysis pipeline."""
    try:
        from models.database import SessionLocal
        from services.autonomous_pipeline import run_autonomous_analysis
        from services.llm_service import LLMService

        db = SessionLocal()
        llm = LLMService()
        try:
            run_autonomous_analysis(dataset_id, db, owner_id, llm)
            logger.info(f"Autonomous analysis completed for dataset {dataset_id}")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"Autonomous task failed for {dataset_id}: {exc}")
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.build_rag_index_task")
def build_rag_index_task(dataset_id: str, file_path: str, file_type: str, dataset_name: str):
    """Build FAISS/embedding vector index for RAG chat."""
    try:
        from services.data_processor import load_dataset
        from services.rag_service import build_index

        df = load_dataset(file_path, file_type)
        success = build_index(df, dataset_id, dataset_name)
        logger.info(f"RAG index build {'succeeded' if success else 'failed'} for {dataset_id}")
        return {"success": success, "dataset_id": dataset_id}
    except Exception as e:
        logger.error(f"RAG index task error: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(name="tasks.evaluate_alerts_task", rate_limit="100/m")
def evaluate_alerts_task(dataset_id: str):
    """Evaluate all active alerts for a specific dataset."""
    try:
        from models.database import SessionLocal, Alert, Dataset
        from services.data_processor import load_dataset
        from services.alert_service import AlertService

        db = SessionLocal()
        svc = AlertService()
        try:
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if not dataset or dataset.status != "ready":
                return

            alerts = db.query(Alert).filter(
                Alert.dataset_id == dataset_id,
                Alert.is_active == True,
            ).all()
            if not alerts:
                return

            df = load_dataset(dataset.file_path, dataset.file_type)
            results = svc.evaluate_all(alerts, df, dataset.name, db)
            logger.info(f"Evaluated {len(results)} alerts for dataset {dataset_id}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Alert evaluation error for {dataset_id}: {e}")


@celery_app.task(name="tasks.evaluate_all_active_alerts")
def evaluate_all_active_alerts():
    """Periodic task: evaluate all active alerts across all datasets."""
    try:
        from models.database import SessionLocal, Alert

        db = SessionLocal()
        try:
            dataset_ids = (
                db.query(Alert.dataset_id)
                .filter(Alert.is_active == True, Alert.dataset_id.isnot(None))
                .distinct()
                .all()
            )
            for (did,) in dataset_ids:
                evaluate_alerts_task.delay(did)
            logger.info(f"Scheduled alert evaluation for {len(dataset_ids)} datasets")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Global alert evaluation error: {e}")


@celery_app.task(name="tasks.send_scheduled_reports")
def send_scheduled_reports():
    """Daily task: send all due scheduled reports via email."""
    try:
        from models.database import SessionLocal
        from services.scheduled_reports import process_due_reports
        db = SessionLocal()
        try:
            sent = process_due_reports(db)
            logger.info(f"Scheduled reports: {sent} sent")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Scheduled reports error: {e}")


# ─── Phase 9: Proactive Intelligence Tasks ───────────────────

@celery_app.task(name="tasks.proactive_scan_all")
def proactive_scan_all():
    """
    Periodic beat task — runs proactive intelligence scan for all active users.
    Detects anomalies, trend shifts, and record values, then pushes insights.
    """
    import asyncio
    try:
        from services.proactive_monitor import run_proactive_scan
        stats = asyncio.run(run_proactive_scan())
        logger.info(f"Proactive scan completed: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Proactive scan task error: {e}")
        return {"error": str(e)}


@celery_app.task(name="tasks.proactive_scan_user")
def proactive_scan_user(user_id: str):
    """On-demand proactive scan for a specific user."""
    import asyncio
    try:
        from services.proactive_monitor import run_proactive_scan
        stats = asyncio.run(run_proactive_scan(user_id=user_id))
        logger.info(f"Proactive scan for user {user_id}: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Proactive scan user task error: {e}")
        return {"error": str(e)}


# ─── Phase 14: Personalized Digest Tasks ─────────────────────

@celery_app.task(name="tasks.send_digest_all")
def send_digest_all():
    """
    Periodic beat task — sends personalized AI digest to all enabled users.
    Runs daily at 08:00 UTC.
    """
    import asyncio
    try:
        from models.database import SessionLocal, DigestConfig
        from services.digest_generator import send_digest_to_user
        from datetime import datetime

        db = SessionLocal()
        try:
            now = datetime.utcnow()
            configs = db.query(DigestConfig).filter(DigestConfig.is_enabled == True).all()
            stats = {"sent": 0, "errors": 0}
            for config in configs:
                try:
                    asyncio.run(send_digest_to_user(config.user_id, config))
                    stats["sent"] += 1
                except Exception as e:
                    logger.error(f"Digest send error for user {config.user_id}: {e}")
                    stats["errors"] += 1
            logger.info(f"Digest batch complete: {stats}")
            return stats
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Digest all task error: {e}")
        return {"error": str(e)}
