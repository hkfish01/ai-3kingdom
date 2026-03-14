"""agent abilities and duplicate display names

Revision ID: 20260314_0004
Revises: 20260314_0003
Create Date: 2026-03-14 16:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0004"
down_revision = "20260314_0003"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def _has_index(inspector: sa.Inspector, table: str, index: str) -> bool:
    return any(i.get("name") == index for i in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "agents", "martial"):
        op.add_column("agents", sa.Column("martial", sa.Integer(), nullable=False, server_default="50"))
    if not _has_column(inspector, "agents", "intelligence"):
        op.add_column("agents", sa.Column("intelligence", sa.Integer(), nullable=False, server_default="50"))
    if not _has_column(inspector, "agents", "charisma"):
        op.add_column("agents", sa.Column("charisma", sa.Integer(), nullable=False, server_default="50"))
    if not _has_column(inspector, "agents", "politics"):
        op.add_column("agents", sa.Column("politics", sa.Integer(), nullable=False, server_default="50"))

    # Allow duplicate display names by replacing unique index with normal index.
    for idx in inspector.get_indexes("agents"):
        if idx.get("name") == "ix_agents_name" and idx.get("unique"):
            op.drop_index("ix_agents_name", table_name="agents")
            break

    if not _has_index(sa.inspect(bind), "agents", "ix_agents_name"):
        op.create_index("ix_agents_name", "agents", ["name"], unique=False)


def downgrade() -> None:
    # Keep backward compatibility: do not force re-adding unique constraint on agent names.
    pass
