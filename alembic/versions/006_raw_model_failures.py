"""Add raw model failure telemetry table.

Revision ID: 006
Revises: 005
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_model_failures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_number", sa.Integer, nullable=True),
        sa.Column("failure_type", sa.String(100), nullable=False),
        sa.Column("first_failing_stage", sa.String(100), nullable=True),
        sa.Column("sidecar_latency_ms", sa.Float, nullable=True),
        sa.Column("evidence_ids", JSONB, server_default="[]"),
        sa.Column("risk_flags", JSONB, server_default="[]"),
        sa.Column("sidecar_stage_metrics", JSONB, server_default="[]"),
        sa.Column("failure_payload", JSONB, server_default="{}"),
        sa.Column("failure_body_summary", sa.Text, server_default=""),
        sa.Column("retrain_candidate", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_raw_model_failures_simulation_id", "raw_model_failures", ["simulation_id"])
    op.create_index("ix_raw_model_failures_agent_id", "raw_model_failures", ["agent_id"])
    op.create_index("ix_raw_model_failures_first_failing_stage", "raw_model_failures", ["first_failing_stage"])


def downgrade() -> None:
    op.drop_index("ix_raw_model_failures_first_failing_stage", table_name="raw_model_failures")
    op.drop_index("ix_raw_model_failures_agent_id", table_name="raw_model_failures")
    op.drop_index("ix_raw_model_failures_simulation_id", table_name="raw_model_failures")
    op.drop_table("raw_model_failures")
