"""Security utilities."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
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


def create_access_token(email: str, expires_delta: Optional[timedelta] = None) -> tuple[str, int]:
    """Create a JWT access token.

    Returns:
        (token, expires_in_seconds)
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": email,
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.access_token_secret,
        algorithm="HS256",
    )

    return encoded_jwt, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> Optional[str]:
    """Decode and verify JWT token.

    Returns:
        Email address if valid, None otherwise.
    """
    try:
        payload = jwt.decode(
            token,
            settings.access_token_secret,
            algorithms=["HS256"],
        )
        email: str = payload.get("sub")
        if email is None:
            return None
        return email
    except jwt.PyJWTError:
        return None


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
