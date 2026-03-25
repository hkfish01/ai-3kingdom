"""add user email/admin and password reset codes

Revision ID: 20260314_0003
Revises: 20260314_0002
Create Date: 2026-03-14 17:50:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260314_0003"
down_revision = "20260314_0002"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def _has_index(inspector: sa.Inspector, table: str, index: str) -> bool:
    return any(i.get("name") == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "users", "email"):
        op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))

    # Backfill generated emails for existing users.
    bind.execute(sa.text("UPDATE users SET email = lower(username || '@local.invalid') WHERE email IS NULL OR email = ''"))

    if not _has_index(inspector, "users", "ix_users_email"):
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not _has_column(inspector, "users", "is_admin"):
        op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))

    if not inspector.has_table("password_reset_codes"):
        op.create_table(
            "password_reset_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("code_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_password_reset_codes_id", "password_reset_codes", ["id"])
        op.create_index("ix_password_reset_codes_user_id", "password_reset_codes", ["user_id"])
        op.create_index("ix_password_reset_codes_email", "password_reset_codes", ["email"])
        op.create_index("ix_password_reset_codes_code_hash", "password_reset_codes", ["code_hash"])
        op.create_index("ix_password_reset_codes_expires_at", "password_reset_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_codes_expires_at", table_name="password_reset_codes")
    op.drop_index("ix_password_reset_codes_code_hash", table_name="password_reset_codes")
    op.drop_index("ix_password_reset_codes_email", table_name="password_reset_codes")
    op.drop_index("ix_password_reset_codes_user_id", table_name="password_reset_codes")
    op.drop_index("ix_password_reset_codes_id", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")

    # Keep users.email/is_admin for backward compatibility with running data.
