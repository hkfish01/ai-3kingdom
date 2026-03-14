"""add message read/reply flags

Revision ID: 20260314_0005
Revises: 20260314_0004
Create Date: 2026-03-14 18:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20260314_0005"
down_revision: Union[str, None] = "20260314_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_column(inspector, "messages", "read_at"):
        return

    op.add_column("messages", sa.Column("read_at", sa.DateTime(), nullable=True))
    op.add_column("messages", sa.Column("replied_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_column(inspector, "messages", "replied_at"):
        op.drop_column("messages", "replied_at")
    if _has_column(inspector, "messages", "read_at"):
        op.drop_column("messages", "read_at")
