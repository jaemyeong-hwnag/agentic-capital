"""Add commission and net_value columns to trades table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("commission", sa.DECIMAL(20, 4), nullable=False, server_default="0"))
    op.add_column("trades", sa.Column("net_value", sa.DECIMAL(20, 4), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("trades", "net_value")
    op.drop_column("trades", "commission")
