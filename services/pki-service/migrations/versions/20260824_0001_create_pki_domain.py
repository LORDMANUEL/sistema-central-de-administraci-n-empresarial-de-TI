"""create PKI certificate and outbox domain

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
    certificate_status = sa.Enum("active", "revoked", name="certificate_status", native_enum=False)
    op.create_table(
        "certificates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issuance_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("serial_hex", sa.String(length=64), nullable=False),
        sa.Column("csr_sha256", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("subject_cn", sa.String(length=255), nullable=False),
        sa.Column("san_uri", sa.String(length=1024), nullable=False),
        sa.Column("certificate_pem", sa.Text(), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", certificate_status, nullable=False),
        sa.Column("replaces_certificate_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["replaces_certificate_id"], ["certificates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint_sha256"),
        sa.UniqueConstraint("issuance_id"),
        sa.UniqueConstraint("serial_hex"),
    )
    op.create_index("ix_certificates_asset_id", "certificates", ["asset_id"])
    op.create_index("ix_certificates_device_id", "certificates", ["device_id"])
    op.create_index("ix_certificates_device_status", "certificates", ["device_id", "status"])
    op.create_index("ix_certificates_expiry", "certificates", ["not_after"])
    op.create_index("ix_certificates_fingerprint_sha256", "certificates", ["fingerprint_sha256"])
    op.create_index("ix_certificates_issuance_id", "certificates", ["issuance_id"])
    op.create_index("ix_certificates_replaces_certificate_id", "certificates", ["replaces_certificate_id"])
    op.create_index("ix_certificates_serial_hex", "certificates", ["serial_hex"])
    op.create_index("ix_certificates_tenant_id", "certificates", ["tenant_id"])
    op.create_index("ix_certificates_tenant_status", "certificates", ["tenant_id", "status"])

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

    op.drop_index("ix_certificates_tenant_status", table_name="certificates")
    op.drop_index("ix_certificates_tenant_id", table_name="certificates")
    op.drop_index("ix_certificates_serial_hex", table_name="certificates")
    op.drop_index("ix_certificates_replaces_certificate_id", table_name="certificates")
    op.drop_index("ix_certificates_issuance_id", table_name="certificates")
    op.drop_index("ix_certificates_fingerprint_sha256", table_name="certificates")
    op.drop_index("ix_certificates_expiry", table_name="certificates")
    op.drop_index("ix_certificates_device_status", table_name="certificates")
    op.drop_index("ix_certificates_device_id", table_name="certificates")
    op.drop_index("ix_certificates_asset_id", table_name="certificates")
    op.drop_table("certificates")
