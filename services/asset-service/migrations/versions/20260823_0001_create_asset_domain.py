"""create asset domain

Revision ID: 20260823_0001
Revises:
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20260823_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("guardian_asset_id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("serial_number", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assets_tenant_id", "assets", ["tenant_id"])
    op.create_index("ix_assets_site_id", "assets", ["site_id"])
    op.create_index("ix_assets_department_id", "assets", ["department_id"])
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_hostname", "assets", ["hostname"])
    op.create_index("ix_assets_serial_number", "assets", ["serial_number"])
    op.create_index("ix_assets_status", "assets", ["status"])

    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("guardian_asset_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guardian_asset_id"], ["assets.guardian_asset_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "external_id", name="uq_external_provider_id"),
    )
    op.create_index("ix_external_identities_guardian_asset_id", "external_identities", ["guardian_asset_id"])

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_external_identities_guardian_asset_id", table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_index("ix_assets_status", table_name="assets")
    op.drop_index("ix_assets_serial_number", table_name="assets")
    op.drop_index("ix_assets_hostname", table_name="assets")
    op.drop_index("ix_assets_asset_type", table_name="assets")
    op.drop_index("ix_assets_department_id", table_name="assets")
    op.drop_index("ix_assets_site_id", table_name="assets")
    op.drop_index("ix_assets_tenant_id", table_name="assets")
    op.drop_table("assets")
