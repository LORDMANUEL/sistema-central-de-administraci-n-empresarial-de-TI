"""create identity users table

Revision ID: 20260821_0001
Revises:
Create Date: 2026-08-21
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260821_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    role_enum = sa.Enum(
        "PLATFORM_ADMIN",
        "ORG_ADMIN",
        "SECURITY_ADMIN",
        "IT_OPERATOR",
        "HELPDESK",
        "AUDITOR",
        "VIEWER",
        name="role",
        native_enum=False,
        length=32,
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "identity_state",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("identity_state")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
