"""create audit domain

Revision ID: 20260824_0001
Revises:
Create Date: 2026-08-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_chain_heads",
        sa.Column("chain_key", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hash", sa.String(length=64), nullable=False, server_default="0" * 64),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("chain_key"),
    )
    op.create_index("ix_audit_chain_heads_tenant_id", "audit_chain_heads", ["tenant_id"], unique=False)

    op.create_table(
        "audit_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("chain_key", sa.String(length=128), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=160), nullable=False),
        sa.Column("source_service", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=96), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain_key", "sequence", name="uq_audit_record_chain_sequence"),
        sa.UniqueConstraint("source_event_id", name="uq_audit_records_source_event_id"),
    )
    for name, columns in (
        ("ix_audit_records_tenant_id", ["tenant_id"]),
        ("ix_audit_records_chain_key", ["chain_key"]),
        ("ix_audit_records_source_event_id", ["source_event_id"]),
        ("ix_audit_records_source_type", ["source_type"]),
        ("ix_audit_records_source_service", ["source_service"]),
        ("ix_audit_records_actor_user_id", ["actor_user_id"]),
        ("ix_audit_records_action", ["action"]),
        ("ix_audit_records_resource_type", ["resource_type"]),
        ("ix_audit_records_resource_id", ["resource_id"]),
        ("ix_audit_records_outcome", ["outcome"]),
        ("ix_audit_records_request_id", ["request_id"]),
        ("ix_audit_records_occurred_at", ["occurred_at"]),
        ("ix_audit_records_ingested_at", ["ingested_at"]),
        ("ix_audit_records_record_hash", ["record_hash"]),
    ):
        op.create_index(name, "audit_records", columns, unique=False)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION guardian_reject_audit_record_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'audit_records is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER guardian_audit_records_append_only
            BEFORE UPDATE OR DELETE ON audit_records
            FOR EACH ROW EXECUTE FUNCTION guardian_reject_audit_record_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS guardian_audit_records_append_only ON audit_records")
        op.execute("DROP FUNCTION IF EXISTS guardian_reject_audit_record_mutation()")
    op.drop_table("audit_records")
    op.drop_table("audit_chain_heads")
