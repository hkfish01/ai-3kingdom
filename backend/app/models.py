from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    agents: Mapped[list["Agent"]] = relationship(back_populates="owner")


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(255), unique=True)
    public_key: Mapped[str] = mapped_column(String(512), default="")
    prosperity: Mapped[float] = mapped_column(Float, default=0.0)
    city_wall: Mapped[int] = mapped_column(Integer, default=300)
    city_tax_rate: Mapped[float] = mapped_column(Float, default=0.05)
    treasury_gold: Mapped[int] = mapped_column(Integer, default=0)
    treasury_food: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    protocol_version: Mapped[str] = mapped_column(String(16), default="1.0")
    rule_version: Mapped[str] = mapped_column(String(16), default="1.0")
    open_for_migration: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(64))
    home_city: Mapped[str] = mapped_column(String(64))
    current_city: Mapped[str] = mapped_column(String(64))

    energy: Mapped[int] = mapped_column(Integer, default=100)
    gold: Mapped[int] = mapped_column(Integer, default=100)
    food: Mapped[int] = mapped_column(Integer, default=100)

    infantry: Mapped[int] = mapped_column(Integer, default=0)
    archer: Mapped[int] = mapped_column(Integer, default=0)
    cavalry: Mapped[int] = mapped_column(Integer, default=0)

    reputation: Mapped[int] = mapped_column(Integer, default=0)
    martial: Mapped[int] = mapped_column(Integer, default=50)
    intelligence: Mapped[int] = mapped_column(Integer, default=50)
    charisma: Mapped[int] = mapped_column(Integer, default=50)
    politics: Mapped[int] = mapped_column(Integer, default=50)
    lord_agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    faction_id: Mapped[int | None] = mapped_column(ForeignKey("factions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    owner: Mapped[User] = relationship(back_populates="agents")


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    city_name: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    energy_cost: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Faction(Base):
    __tablename__ = "factions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    leader_agent_id: Mapped[int] = mapped_column(Integer, index=True)
    home_city: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    to_agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    message_type: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="delivered")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BattleLog(Base):
    __tablename__ = "battle_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    attacker_city: Mapped[str] = mapped_column(String(64), index=True)
    defender_city: Mapped[str] = mapped_column(String(64), index=True)
    attacker_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    defender_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attack_power: Mapped[float] = mapped_column(Float)
    defense_power: Mapped[float] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(16))
    loot_gold: Mapped[int] = mapped_column(Integer, default=0)
    loot_food: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ChronicleEntry(Base):
    __tablename__ = "chronicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    city_name: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class FederationPeer(Base):
    __tablename__ = "federation_peers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    city_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(255), unique=True)
    public_key: Mapped[str] = mapped_column(String(512), default="")
    shared_secret: Mapped[str] = mapped_column(String(255), default="")
    trust_status: Mapped[str] = mapped_column(String(16), default="trusted")
    protocol_version: Mapped[str] = mapped_column(String(16), default="1.0")
    rule_version: Mapped[str] = mapped_column(String(16), default="1.0")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class FederationRequestLog(Base):
    __tablename__ = "federation_request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    request_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source_city: Mapped[str] = mapped_column(String(64), index=True)
    request_type: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class MigrationLog(Base):
    __tablename__ = "migration_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(Integer, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    from_city: Mapped[str] = mapped_column(String(64), index=True)
    to_city: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SystemState(Base):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    last4: Mapped[str] = mapped_column(String(8), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentClaimTicket(Base):
    __tablename__ = "agent_claim_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AgentClaim(Base):
    __tablename__ = "agent_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    human_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DungeonClear(Base):
    __tablename__ = "dungeon_clears"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    dungeon_id: Mapped[str] = mapped_column(String(32), index=True)
    cleared_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AgentProtection(Base):
    __tablename__ = "agent_protections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), unique=True, index=True)
    protected_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    reason: Mapped[str] = mapped_column(String(64), default="battle_loss")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class PvpChallengeDaily(Base):
    __tablename__ = "pvp_challenge_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # UTC date: YYYY-MM-DD
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
