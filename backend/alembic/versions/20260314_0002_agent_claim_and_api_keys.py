"""add api keys and claim tables

Revision ID: 20260314_0002
Revises: 20260314_0001
Create Date: 2026-03-14 03:20:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260314_0002"
down_revision = "20260314_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("key_prefix", sa.String(length=16), nullable=False),
            sa.Column("key_hash", sa.String(length=128), nullable=False),
            sa.Column("last4", sa.String(length=8), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_api_keys_id", "api_keys", ["id"])
        op.create_index("ix_api_keys_owner_user_id", "api_keys", ["owner_user_id"])
        op.create_index("ix_api_keys_agent_id", "api_keys", ["agent_id"])
        op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
        op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    if not inspector.has_table("agent_claim_tickets"):
        op.create_table(
            "agent_claim_tickets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("code_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_agent_claim_tickets_id", "agent_claim_tickets", ["id"])
        op.create_index("ix_agent_claim_tickets_agent_id", "agent_claim_tickets", ["agent_id"], unique=True)
        op.create_index("ix_agent_claim_tickets_code_hash", "agent_claim_tickets", ["code_hash"], unique=True)
        op.create_index("ix_agent_claim_tickets_expires_at", "agent_claim_tickets", ["expires_at"])

    if not inspector.has_table("agent_claims"):
        op.create_table(
            "agent_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("human_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_agent_claims_id", "agent_claims", ["id"])
        op.create_index("ix_agent_claims_human_user_id", "agent_claims", ["human_user_id"])
        op.create_index("ix_agent_claims_agent_id", "agent_claims", ["agent_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agent_claims_agent_id", table_name="agent_claims")
    op.drop_index("ix_agent_claims_human_user_id", table_name="agent_claims")
    op.drop_index("ix_agent_claims_id", table_name="agent_claims")
    op.drop_table("agent_claims")

    op.drop_index("ix_agent_claim_tickets_expires_at", table_name="agent_claim_tickets")
    op.drop_index("ix_agent_claim_tickets_code_hash", table_name="agent_claim_tickets")
    op.drop_index("ix_agent_claim_tickets_agent_id", table_name="agent_claim_tickets")
    op.drop_index("ix_agent_claim_tickets_id", table_name="agent_claim_tickets")
    op.drop_table("agent_claim_tickets")

    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_agent_id", table_name="api_keys")
    op.drop_index("ix_api_keys_owner_user_id", table_name="api_keys")
    op.drop_index("ix_api_keys_id", table_name="api_keys")
    op.drop_table("api_keys")
