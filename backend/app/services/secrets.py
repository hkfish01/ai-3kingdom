import hashlib
import secrets


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_api_key() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def make_claim_code() -> str:
    return f"claim_{secrets.token_urlsafe(24)}"


def make_password(length: int = 24) -> str:
    return secrets.token_urlsafe(length)[:length]


def make_numeric_code(length: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(length))
