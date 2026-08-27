from alembic import op
import sqlalchemy as sa

revision = "20260827_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("device_sessions", sa.Column("device_id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), nullable=False), sa.Column("guardian_asset_id", sa.Uuid(), nullable=False), sa.Column("certificate_serial", sa.String(128), nullable=False), sa.Column("session_id", sa.Uuid(), nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("agent_version", sa.String(128), nullable=False), sa.Column("platform", sa.String(128), nullable=False), sa.Column("platform_version", sa.String(128), nullable=False), sa.Column("current_capabilities", sa.JSON(), nullable=False), sa.Column("capability_version", sa.Integer(), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_device_sessions_tenant_id", "device_sessions", ["tenant_id"])
    op.create_index("ix_device_sessions_guardian_asset_id", "device_sessions", ["guardian_asset_id"])
    op.create_table("device_capability_snapshots", sa.Column("snapshot_id", sa.Uuid(), primary_key=True), sa.Column("device_id", sa.Uuid(), sa.ForeignKey("device_sessions.device_id", ondelete="CASCADE"), nullable=False), sa.Column("capability_version", sa.Integer(), nullable=False), sa.Column("capabilities", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_device_capability_snapshots_device_id", "device_capability_snapshots", ["device_id"])
    op.create_table("outbox_events", sa.Column("event_id", sa.Uuid(), primary_key=True), sa.Column("event_type", sa.String(128), nullable=False), sa.Column("aggregate_id", sa.String(128), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("last_error", sa.String(512)))
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])

def downgrade():
    op.drop_table("outbox_events")
    op.drop_table("device_capability_snapshots")
    op.drop_table("device_sessions")
