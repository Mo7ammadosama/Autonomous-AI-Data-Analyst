"""
Template Service — create dashboards from pre-built templates with column mapping.
"""

import uuid
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class TemplateService:
    """Instantiate a DashboardTemplate into a real Dashboard for a user."""

    def apply_column_mapping(
        self,
        charts_config: List[Dict],
        column_mappings: Dict[str, str],
    ) -> List[Dict]:
        """
        Replace placeholder column names in charts_config with user's actual columns.

        column_mappings: { "placeholder_col": "actual_col_in_dataset" }
        """
        import json
        raw = json.dumps(charts_config)
        for placeholder, actual in column_mappings.items():
            raw = raw.replace(f'"{placeholder}"', f'"{actual}"')
            raw = raw.replace(f"'{placeholder}'", f"'{actual}'")
        try:
            return json.loads(raw)
        except Exception:
            return charts_config

    def create_dashboard_from_template(
        self,
        template,
        dataset_id: str,
        user_id: str,
        column_mappings: Optional[Dict[str, str]],
        db,
    ) -> Dict[str, Any]:
        """
        Instantiate a template into a Dashboard record.
        Returns the new dashboard as a dict.
        """
        from models.database import Dashboard

        mappings = column_mappings or {}
        charts = self.apply_column_mapping(template.charts_config or [], mappings)
        layout = template.layout or {}

        dashboard = Dashboard(
            id=str(uuid.uuid4()),
            title=f"{template.name} Dashboard",
            description=template.description,
            layout={**layout, "from_template": template.id},
            charts=charts,
            dataset_id=dataset_id,
            user_id=user_id,
        )
        db.add(dashboard)

        # Increment usage counter
        template.usage_count = (template.usage_count or 0) + 1

        db.commit()
        db.refresh(dashboard)

        return {
            "id": dashboard.id,
            "title": dashboard.title,
            "description": dashboard.description,
            "charts": dashboard.charts,
            "layout": dashboard.layout,
            "dataset_id": dashboard.dataset_id,
            "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        }


template_service = TemplateService()
