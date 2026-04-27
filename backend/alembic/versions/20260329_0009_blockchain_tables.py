"""add blockchain chain_assets, chain_transactions, chain_collections, market_listings tables and user wallet fields

Revision ID: 20260329_0009
Revises: 20260319_0008
Create Date: 2026-03-29 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260329_0009"
down_revision: Union[str, None] = "20260319_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # -- Users: add wallet columns --
    if "wallet_address" not in [c["name"] for c in inspector.get_columns("users")]:
        op.add_column("users", sa.Column("wallet_address", sa.String(128), nullable=True))
        op.create_index("ix_users_wallet_address", "users", ["wallet_address"], unique=True)
    if "wallet_bound_at" not in [c["name"] for c in inspector.get_columns("users")]:
        op.add_column("users", sa.Column("wallet_bound_at", sa.DateTime, nullable=True))

    # -- chain_assets --
    if not inspector.has_table("chain_assets"):
        op.create_table(
            "chain_assets",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("chain_id", sa.String(64), nullable=False),
            sa.Column("chain_token_id", sa.String(128), server_default=""),
            sa.Column("chain_tx_hash", sa.String(128), server_default=""),
            sa.Column("asset_type", sa.String(16), nullable=False),
            sa.Column("collection_id", sa.String(64), server_default=""),
            sa.Column("owner_address", sa.String(128), nullable=False),
            sa.Column("name", sa.String(128), server_default=""),
            sa.Column("token_uri", sa.String(512), server_default=""),
            sa.Column("metadata_json", sa.Text, server_default="{}"),
            sa.Column("status", sa.String(16), server_default="active"),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_chain_assets_id", "chain_assets", ["id"])
        op.create_index("ix_chain_assets_uuid", "chain_assets", ["uuid"], unique=True)
        op.create_index("ix_chain_assets_chain_id", "chain_assets", ["chain_id"])
        op.create_index("ix_chain_assets_chain_token_id", "chain_assets", ["chain_token_id"])
        op.create_index("ix_chain_assets_asset_type", "chain_assets", ["asset_type"])
        op.create_index("ix_chain_assets_collection_id", "chain_assets", ["collection_id"])
        op.create_index("ix_chain_assets_owner_address", "chain_assets", ["owner_address"])
        op.create_index("ix_chain_assets_status", "chain_assets", ["status"])

    # -- chain_transactions --
    if not inspector.has_table("chain_transactions"):
        op.create_table(
            "chain_transactions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("chain_id", sa.String(64), nullable=False),
            sa.Column("tx_hash", sa.String(128), nullable=False),
            sa.Column("from_address", sa.String(128), server_default=""),
            sa.Column("to_address", sa.String(128), server_default=""),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("asset_uuid", sa.String(36), server_default=""),
            sa.Column("amount", sa.String(64), server_default="1"),
            sa.Column("status", sa.String(16), server_default="pending"),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("confirmed_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_chain_transactions_id", "chain_transactions", ["id"])
        op.create_index("ix_chain_transactions_chain_id", "chain_transactions", ["chain_id"])
        op.create_index("ix_chain_transactions_tx_hash", "chain_transactions", ["tx_hash"], unique=True)
        op.create_index("ix_chain_transactions_from_address", "chain_transactions", ["from_address"])
        op.create_index("ix_chain_transactions_to_address", "chain_transactions", ["to_address"])
        op.create_index("ix_chain_transactions_action", "chain_transactions", ["action"])
        op.create_index("ix_chain_transactions_asset_uuid", "chain_transactions", ["asset_uuid"])
        op.create_index("ix_chain_transactions_status", "chain_transactions", ["status"])

    # -- chain_collections --
    if not inspector.has_table("chain_collections"):
        op.create_table(
            "chain_collections",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("collection_id", sa.String(64), nullable=False),
            sa.Column("chain_id", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("description", sa.Text, server_default=""),
            sa.Column("base_uri", sa.String(512), server_default=""),
            sa.Column("tx_hash", sa.String(128), server_default=""),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_chain_collections_id", "chain_collections", ["id"])
        op.create_index("ix_chain_collections_collection_id", "chain_collections", ["collection_id"], unique=True)
        op.create_index("ix_chain_collections_chain_id", "chain_collections", ["chain_id"])

    # -- market_listings --
    if not inspector.has_table("market_listings"):
        op.create_table(
            "market_listings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("listing_id", sa.String(64), nullable=False),
            sa.Column("chain_id", sa.String(64), nullable=False),
            sa.Column("seller", sa.String(128), nullable=False),
            sa.Column("token_id", sa.String(128), nullable=False),
            sa.Column("asset_uuid", sa.String(36), server_default=""),
            sa.Column("price", sa.String(64), nullable=False),
            sa.Column("price_symbol", sa.String(32), nullable=False),
            sa.Column("tx_hash", sa.String(128), server_default=""),
            sa.Column("status", sa.String(16), server_default="active"),
            sa.Column("expires_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_market_listings_id", "market_listings", ["id"])
        op.create_index("ix_market_listings_listing_id", "market_listings", ["listing_id"], unique=True)
        op.create_index("ix_market_listings_chain_id", "market_listings", ["chain_id"])
        op.create_index("ix_market_listings_seller", "market_listings", ["seller"])
        op.create_index("ix_market_listings_token_id", "market_listings", ["token_id"])
        op.create_index("ix_market_listings_asset_uuid", "market_listings", ["asset_uuid"])
        op.create_index("ix_market_listings_status", "market_listings", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if inspector.has_table("market_listings"):
        op.drop_table("market_listings")
    if inspector.has_table("chain_collections"):
        op.drop_table("chain_collections")
    if inspector.has_table("chain_transactions"):
        op.drop_table("chain_transactions")
    if inspector.has_table("chain_assets"):
        op.drop_table("chain_assets")

    if "wallet_bound_at" in [c["name"] for c in inspector.get_columns("users")]:
        op.drop_column("users", "wallet_bound_at")
    if "wallet_address" in [c["name"] for c in inspector.get_columns("users")]:
        op.drop_index("ix_users_wallet_address", table_name="users")
        op.drop_column("users", "wallet_address")
