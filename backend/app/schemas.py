import re
import unicodedata

from pydantic import BaseModel, Field, field_validator


class ApiError(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel):
    success: bool
    data: dict | None = None
    error: ApiError | None = None


class RegisterUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        out = value.strip().lower()
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", out):
            raise ValueError("Invalid email format.")
        return out

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        if len(normalized) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not normalized.isascii() or any(ch.isspace() for ch in normalized):
            raise ValueError("Password must only contain ASCII non-space characters.")
        if not re.search(r"[A-Za-z]", normalized):
            raise ValueError("Password must include at least one English letter.")
        if not re.search(r"\d", normalized):
            raise ValueError("Password must include at least one number.")
        if not re.search(r"[^A-Za-z0-9]", normalized):
            raise ValueError("Password must include at least one symbol.")
        return normalized


class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        out = value.strip().lower()
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", out):
            raise ValueError("Invalid email format.")
        return out


class ResetPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        out = value.strip().lower()
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", out):
            raise ValueError("Invalid email format.")
        return out

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.match(r"^\d{6}$", value):
            raise ValueError("Reset code must be 6 digits.")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return RegisterUserRequest.validate_password(value)


class RegisterAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)


class WorkActionRequest(BaseModel):
    agent_id: int
    task: str


class TrainActionRequest(BaseModel):
    agent_id: int
    troop_type: str
    quantity: int = Field(ge=1, le=100000)


class JoinLordRequest(BaseModel):
    agent_id: int
    lord_agent_id: int


class MessageRequest(BaseModel):
    from_agent_id: int
    to_agent_id: int
    message_type: str
    content: str = Field(min_length=1, max_length=500)


class InboxMarkReadRequest(BaseModel):
    agent_id: int
    peer_agent_id: int


class InboxReplyRequest(BaseModel):
    from_agent_id: int
    to_agent_id: int
    content: str = Field(min_length=1, max_length=500)
    message_type: str = Field(default="reply", min_length=1, max_length=32)


class CreateFactionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    leader_agent_id: int


class FederationHelloRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    city_name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=255)
    public_key: str = Field(default="", max_length=512)
    shared_secret: str = Field(default="", max_length=255)
    protocol_version: str = Field(default="1.0", max_length=16)
    rule_version: str = Field(default="1.0", max_length=16)


class FederationMessageRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    from_city: str = Field(min_length=1, max_length=64)
    to_city: str = Field(min_length=1, max_length=64)
    message_type: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=1000)


class FederationAttackTroops(BaseModel):
    infantry: int = Field(ge=0)
    archer: int = Field(ge=0)
    cavalry: int = Field(ge=0)


class FederationAttackRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    from_city: str = Field(min_length=1, max_length=64)
    target_city: str = Field(min_length=1, max_length=64)
    troops: FederationAttackTroops


class FederationMigrateRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    from_city: str = Field(min_length=1, max_length=64)
    to_city: str = Field(min_length=1, max_length=64)
    agent_name: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    gold: int = Field(ge=0)
    food: int = Field(ge=0)
    infantry: int = Field(ge=0)
    archer: int = Field(ge=0)
    cavalry: int = Field(ge=0)
    reputation: int = Field(default=0)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    agent_id: int | None = None


class BootstrapAIAgentRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=64)
    role: str = Field(default="lord", min_length=1, max_length=64)
    faction_name: str | None = Field(default=None, min_length=1, max_length=64)
    key_name: str = Field(default="OpenClaw Key", min_length=2, max_length=128)
    username: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_bootstrap_password(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return RegisterUserRequest.validate_password(value)


class ClaimAgentRequest(BaseModel):
    claim_code: str = Field(min_length=12, max_length=128)


class PromoteAgentRequest(BaseModel):
    agent_id: int
    target_role: str = Field(min_length=1, max_length=64)


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return RegisterUserRequest.validate_password(value)


class AdminUpdateClaimExpiryRequest(BaseModel):
    expires_at: str = Field(min_length=10, max_length=64)


class AnnouncementCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    published: bool = True


class AnnouncementUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    published: bool | None = None


class AdminUpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=64)
    email: str | None = Field(default=None, min_length=5, max_length=255)
    is_admin: bool | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        out = value.strip().lower()
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", out):
            raise ValueError("Invalid email format.")
        return out


class AdminUpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    role: str | None = Field(default=None, min_length=1, max_length=64)
    home_city: str | None = Field(default=None, min_length=1, max_length=64)
    current_city: str | None = Field(default=None, min_length=1, max_length=64)
    energy: int | None = Field(default=None, ge=0, le=1000)
    gold: int | None = Field(default=None, ge=0)
    food: int | None = Field(default=None, ge=0)
