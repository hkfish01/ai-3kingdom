"""add combat p0 state tables

Revision ID: 20260319_0008
Revises: 20260319_0007
Create Date: 2026-03-19 23:55:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20260319_0008"
down_revision: Union[str, None] = "20260319_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("dungeon_clears"):
        op.create_table(
            "dungeon_clears",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("dungeon_id", sa.String(length=32), nullable=False),
            sa.Column("cleared_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_dungeon_clears_id", "dungeon_clears", ["id"])
        op.create_index("ix_dungeon_clears_agent_id", "dungeon_clears", ["agent_id"])
        op.create_index("ix_dungeon_clears_dungeon_id", "dungeon_clears", ["dungeon_id"])
        op.create_index(
            "ux_dungeon_clears_agent_dungeon",
            "dungeon_clears",
            ["agent_id", "dungeon_id"],
            unique=True,
        )

    if not inspector.has_table("agent_protections"):
        op.create_table(
            "agent_protections",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("protected_until", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(length=64), nullable=False, server_default="battle_loss"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_agent_protections_id", "agent_protections", ["id"])
        op.create_index("ix_agent_protections_agent_id", "agent_protections", ["agent_id"], unique=True)
        op.create_index("ix_agent_protections_protected_until", "agent_protections", ["protected_until"])

    if not inspector.has_table("pvp_challenge_daily"):
        op.create_table(
            "pvp_challenge_daily",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("day", sa.String(length=10), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_pvp_challenge_daily_id", "pvp_challenge_daily", ["id"])
        op.create_index("ix_pvp_challenge_daily_agent_id", "pvp_challenge_daily", ["agent_id"])
        op.create_index("ix_pvp_challenge_daily_day", "pvp_challenge_daily", ["day"])
        op.create_index(
            "ux_pvp_challenge_daily_agent_day",
            "pvp_challenge_daily",
            ["agent_id", "day"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("pvp_challenge_daily"):
        op.drop_index("ux_pvp_challenge_daily_agent_day", table_name="pvp_challenge_daily")
        op.drop_index("ix_pvp_challenge_daily_day", table_name="pvp_challenge_daily")
        op.drop_index("ix_pvp_challenge_daily_agent_id", table_name="pvp_challenge_daily")
        op.drop_index("ix_pvp_challenge_daily_id", table_name="pvp_challenge_daily")
        op.drop_table("pvp_challenge_daily")

    if inspector.has_table("agent_protections"):
        op.drop_index("ix_agent_protections_protected_until", table_name="agent_protections")
        op.drop_index("ix_agent_protections_agent_id", table_name="agent_protections")
        op.drop_index("ix_agent_protections_id", table_name="agent_protections")
        op.drop_table("agent_protections")

    if inspector.has_table("dungeon_clears"):
        op.drop_index("ux_dungeon_clears_agent_dungeon", table_name="dungeon_clears")
        op.drop_index("ix_dungeon_clears_dungeon_id", table_name="dungeon_clears")
        op.drop_index("ix_dungeon_clears_agent_id", table_name="dungeon_clears")
        op.drop_index("ix_dungeon_clears_id", table_name="dungeon_clears")
        op.drop_table("dungeon_clears")
