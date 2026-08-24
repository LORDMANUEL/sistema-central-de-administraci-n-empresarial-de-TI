"""create enrollment domain

Revision ID: 20260824_0001
Revises:
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    enrollment_status = sa.Enum(
        "pending",
        "certificate_issued",
        "enrolled",
        "failed",
        name="enrollment_status",
        native_enum=False,
    )

    op.create_table(
        "enrollment_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_hint", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserved_enrollment_id", sa.String(length=36), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_device_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_enrollment_tokens_asset_id", "enrollment_tokens", ["asset_id"])
    op.create_index("ix_enrollment_tokens_consumed_device_id", "enrollment_tokens", ["consumed_device_id"])
    op.create_index("ix_enrollment_tokens_created_by_user_id", "enrollment_tokens", ["created_by_user_id"])
    op.create_index("ix_enrollment_tokens_expires_at", "enrollment_tokens", ["expires_at"])
    op.create_index("ix_enrollment_tokens_reserved_enrollment_id", "enrollment_tokens", ["reserved_enrollment_id"])
    op.create_index("ix_enrollment_tokens_tenant_consumed", "enrollment_tokens", ["tenant_id", "consumed_at"])
    op.create_index("ix_enrollment_tokens_tenant_expiry", "enrollment_tokens", ["tenant_id", "expires_at"])
    op.create_index("ix_enrollment_tokens_tenant_id", "enrollment_tokens", ["tenant_id"])
    op.create_index("ix_enrollment_tokens_token_hash", "enrollment_tokens", ["token_hash"])

    op.create_table(
        "device_enrollments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("token_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("csr_sha256", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("issuance_id", sa.String(length=36), nullable=False),
        sa.Column("status", enrollment_status, nullable=False),
        sa.Column("certificate_id", sa.String(length=36), nullable=True),
        sa.Column("certificate_serial_hex", sa.String(length=64), nullable=True),
        sa.Column("certificate_fingerprint_sha256", sa.String(length=64), nullable=True),
        sa.Column("certificate_pem", sa.Text(), nullable=True),
        sa.Column("ca_chain_pem", sa.Text(), nullable=True),
        sa.Column("certificate_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["token_id"], ["enrollment_tokens.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
        sa.UniqueConstraint("issuance_id"),
        sa.UniqueConstraint("token_id"),
    )
    op.create_index("ix_device_enrollments_asset_id", "device_enrollments", ["asset_id"])
    op.create_index("ix_device_enrollments_asset_status", "device_enrollments", ["asset_id", "status"])
    op.create_index("ix_device_enrollments_certificate_id", "device_enrollments", ["certificate_id"])
    op.create_index("ix_device_enrollments_device_id", "device_enrollments", ["device_id"])
    op.create_index("ix_device_enrollments_issuance_id", "device_enrollments", ["issuance_id"])
    op.create_index("ix_device_enrollments_tenant_id", "device_enrollments", ["tenant_id"])
    op.create_index("ix_device_enrollments_tenant_status", "device_enrollments", ["tenant_id", "status"])
    op.create_index("ix_device_enrollments_token_id", "device_enrollments", ["token_id"])

    op.create_table(
        "outbox_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_table("outbox_events")

    op.drop_index("ix_device_enrollments_token_id", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_tenant_status", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_tenant_id", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_issuance_id", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_device_id", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_certificate_id", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_asset_status", table_name="device_enrollments")
    op.drop_index("ix_device_enrollments_asset_id", table_name="device_enrollments")
    op.drop_table("device_enrollments")

    op.drop_index("ix_enrollment_tokens_token_hash", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_tenant_id", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_tenant_expiry", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_tenant_consumed", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_reserved_enrollment_id", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_expires_at", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_created_by_user_id", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_consumed_device_id", table_name="enrollment_tokens")
    op.drop_index("ix_enrollment_tokens_asset_id", table_name="enrollment_tokens")
    op.drop_table("enrollment_tokens")
