"""Password hashing and verification using PBKDF2-SHA256."""

from passlib.context import CryptContext

# Use pbkdf2_sha256 to avoid bcrypt backend issues & length limits.
_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def hash_password(plain: str) -> str:
    """Hash a plain-text password. Use for registration and password updates."""
    return _context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a hash. Returns True if match."""
    return _context.verify(plain, hashed)
