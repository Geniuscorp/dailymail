"""Security utilities."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import jwt
import re
import secrets
import string

from app.core.config import get_settings

settings = get_settings()
pwd_context = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        pwd_context.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, InvalidHash):
        return False


ADMIN_SCOPE = "admin"


def _create_token(subject: str, scope: str, expires_delta: Optional[timedelta], default_minutes: int) -> tuple[str, int]:
    if expires_delta is None:
        expires_delta = timedelta(minutes=default_minutes)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": subject,
        "scope": scope,
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.access_token_secret,
        algorithm="HS256",
    )

    return encoded_jwt, int(expires_delta.total_seconds())


def _decode_token(token: str, expected_scope: str) -> Optional[str]:
    try:
        payload = jwt.decode(
            token,
            settings.access_token_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        return None

    if payload.get("scope") != expected_scope:
        return None
    subject: Optional[str] = payload.get("sub")
    return subject


def create_admin_token(username: str, expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """Create a JWT access token for an admin user."""
    return _create_token(
        username, ADMIN_SCOPE, expires_delta, settings.admin_token_expire_minutes
    )


def decode_admin_token(token: str) -> Optional[str]:
    """Decode and verify an admin JWT; returns the admin username."""
    return _decode_token(token, ADMIN_SCOPE)


# Mailbox sessions are opaque, DB-backed tokens, not JWTs: a mailbox is a
# shared, long-lived credential (like mail.tm), so it must be revocable on
# logout or password change instead of only expiring on its own schedule.
def generate_session_token() -> str:
    """Generate a new opaque mailbox session token (the value given to the client)."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a session token for storage/lookup.

    The token already has 256 bits of entropy from a CSPRNG, so a fast hash is
    enough here (unlike a password): there is nothing to brute-force offline.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Local parts are generating by us and also come from clients (prefix/custom
# batch addresses), so they are checked before they reach the database.
LOCAL_PART_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_ADDRESS_LENGTH = 254


def normalize_address(address: str, domain: str) -> str:
    """Validate an address against the service domain and return it lowercased.

    Raises:
        ValueError: If the address is malformed or belongs to another domain.
    """
    candidate = (address or "").strip().lower()
    if len(candidate) > MAX_ADDRESS_LENGTH or candidate.count("@") != 1:
        raise ValueError(f"'{address}' is not a valid email address")

    local_part, _, address_domain = candidate.partition("@")
    if address_domain != domain.lower():
        raise ValueError(f"Address '{candidate}' must belong to the configured domain @{domain}")
    if not LOCAL_PART_PATTERN.match(local_part):
        raise ValueError(f"Local part '{local_part}' is not valid")

    return candidate


def generate_random_address(length: int = 16, prefix: Optional[str] = None) -> str:
    """Generate a random email address.

    Args:
        length: Length of random part (not including prefix)
        prefix: Optional prefix
    """
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(length))

    if prefix:
        address = f"{prefix}{random_part}"
    else:
        address = random_part

    return address


def generate_batch_addresses(quantity: int, prefix: Optional[str] = None) -> list[str]:
    """Generate multiple addresses for a batch.

    Args:
        quantity: Number of addresses to generate
        prefix: Optional prefix (will be followed by 001, 002, etc.)
    """
    addresses = []

    if prefix:
        for i in range(1, quantity + 1):
            address = f"{prefix}{i:03d}"
            addresses.append(address)
    else:
        for _ in range(quantity):
            address = generate_random_address()
            addresses.append(address)

    return addresses


def validate_email_format(email: str) -> bool:
    """Validate basic email format."""
    # Basic validation - more detailed validation done by EmailStr
    return "@" in email and len(email) > 3


def is_reserved_address(address: str) -> bool:
    """Check if address is reserved/invalid."""
    reserved = {
        "admin",
        "noreply",
        "mail",
        "support",
        "info",
        "webmaster",
        "postmaster",
        "nobody",
        "root",
        "system",
    }

    local_part = address.split("@")[0].lower()
    return local_part in reserved
