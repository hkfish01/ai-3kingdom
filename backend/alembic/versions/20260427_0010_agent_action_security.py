"""add api key policy columns and agent action events

Revision ID: 20260427_0010
Revises: 20260329_0009
Create Date: 2026-04-27 11:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260427_0010"
down_revision: Union[str, None] = "20260329_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return column in [col["name"] for col in inspector.get_columns(table)]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if _has_column(inspector, "api_keys", "scope_json") is False:
        op.add_column("api_keys", sa.Column("scope_json", sa.Text(), nullable=False, server_default="[]"))
    if _has_column(inspector, "api_keys", "rate_limit") is False:
        op.add_column("api_keys", sa.Column("rate_limit", sa.String(length=32), nullable=False, server_default="60/min"))
    if _has_column(inspector, "api_keys", "allowed_actions_json") is False:
        op.add_column("api_keys", sa.Column("allowed_actions_json", sa.Text(), nullable=False, server_default="[]"))
    if _has_column(inspector, "api_keys", "expires_at") is False:
        op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(), nullable=True))

    if not inspector.has_table("agent_action_events"):
        op.create_table(
            "agent_action_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("api_key_id", sa.Integer(), sa.ForeignKey("api_keys.id"), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action_type", sa.String(length=32), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
            sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("error_code", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("error_message", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_agent_action_events_id", "agent_action_events", ["id"])
        op.create_index("ix_agent_action_events_agent_id", "agent_action_events", ["agent_id"])
        op.create_index("ix_agent_action_events_api_key_id", "agent_action_events", ["api_key_id"])
        op.create_index("ix_agent_action_events_owner_user_id", "agent_action_events", ["owner_user_id"])
        op.create_index("ix_agent_action_events_action_type", "agent_action_events", ["action_type"])
        op.create_index("ix_agent_action_events_status", "agent_action_events", ["status"])
        op.create_index("ix_agent_action_events_created_at", "agent_action_events", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("agent_action_events"):
        op.drop_table("agent_action_events")

    if _has_column(inspector, "api_keys", "expires_at"):
        op.drop_column("api_keys", "expires_at")
    if _has_column(inspector, "api_keys", "allowed_actions_json"):
        op.drop_column("api_keys", "allowed_actions_json")
    if _has_column(inspector, "api_keys", "rate_limit"):
        op.drop_column("api_keys", "rate_limit")
    if _has_column(inspector, "api_keys", "scope_json"):
        op.drop_column("api_keys", "scope_json")
