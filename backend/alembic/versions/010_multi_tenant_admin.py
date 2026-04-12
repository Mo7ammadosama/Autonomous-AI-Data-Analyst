"""multi_tenant_admin

Revision ID: 010_multi_tenant_admin
Revises: 009_phase9_17
Create Date: 2026-03-18 01:00:00.000000

Adds suspension columns to workspaces table for Phase 18 — Multi-Tenant Admin System.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "010_multi_tenant_admin"
down_revision: Union[str, Sequence[str], None] = "009_phase9_17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("is_suspended", sa.Boolean(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("suspended_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("suspended_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("suspended_at")
        batch_op.drop_column("suspended_reason")
        batch_op.drop_column("is_suspended")
