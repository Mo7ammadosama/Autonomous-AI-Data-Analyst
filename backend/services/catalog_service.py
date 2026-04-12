"""
Catalog Service — auto-index datasets and columns into the Data Catalog.
"""

import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CatalogService:

    def sync_dataset(self, dataset_id: str, db) -> None:
        """
        Auto-catalog a dataset and each of its columns as CatalogEntry records.
        Called after a dataset upload or import completes.
        Idempotent — updates existing entries if they already exist.
        """
        from models.database import Dataset, CatalogEntry

        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            return

        # Upsert dataset-level entry
        entry = db.query(CatalogEntry).filter(
            CatalogEntry.resource_type == "dataset",
            CatalogEntry.resource_id == dataset_id,
        ).first()

        if not entry:
            entry = CatalogEntry(
                resource_type="dataset",
                resource_id=dataset_id,
                name=dataset.name,
                description=dataset.description or f"Dataset with {dataset.row_count or 0} rows",
                owner_id=dataset.owner_id,
                tags=[],
                lineage={"source": "upload"},
            )
            db.add(entry)
        else:
            entry.name = dataset.name
            entry.last_accessed = datetime.utcnow()

        # Upsert column-level entries
        columns_meta = dataset.columns_meta or []
        for col_meta in columns_meta:
            col_name = col_meta.get("name", "")
            if not col_name:
                continue
            col_resource_id = f"{dataset_id}::{col_name}"
            col_entry = db.query(CatalogEntry).filter(
                CatalogEntry.resource_type == "column",
                CatalogEntry.resource_id == col_resource_id,
            ).first()

            if not col_entry:
                col_entry = CatalogEntry(
                    resource_type="column",
                    resource_id=col_resource_id,
                    name=col_name,
                    description=f"{col_meta.get('type', 'unknown')} column in {dataset.name}",
                    owner_id=dataset.owner_id,
                    tags=[col_meta.get("type", "")],
                    lineage={"dataset_id": dataset_id, "dtype": col_meta.get("dtype", "")},
                )
                db.add(col_entry)

        db.commit()
        logger.info(f"Catalog synced for dataset {dataset_id}")

    def record_access(self, resource_type: str, resource_id: str, db) -> None:
        """Increment usage count and update last_accessed for a catalog entry."""
        from models.database import CatalogEntry
        entry = db.query(CatalogEntry).filter(
            CatalogEntry.resource_type == resource_type,
            CatalogEntry.resource_id == resource_id,
        ).first()
        if entry:
            entry.usage_count = (entry.usage_count or 0) + 1
            entry.last_accessed = datetime.utcnow()
            db.commit()


catalog_service = CatalogService()
