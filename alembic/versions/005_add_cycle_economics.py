"""Add cycle economics fields.

Revision ID: 005
Revises: 004
Create Date: 2026-05-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_cycles", sa.Column("ai_cost_krw", sa.Float(), nullable=False, server_default="0"))
    op.add_column("agent_cycles", sa.Column("net_pnl_krw", sa.Float(), nullable=True))
    op.add_column("agent_cycles", sa.Column("decision_roi", sa.Float(), nullable=True))
    op.add_column("agent_cycles", sa.Column("economics_snapshot", JSONB, nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("agent_cycles", "economics_snapshot")
    op.drop_column("agent_cycles", "decision_roi")
    op.drop_column("agent_cycles", "net_pnl_krw")
    op.drop_column("agent_cycles", "ai_cost_krw")
