import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config.settings import settings

# Use bcrypt for password hashing.
# We use a dedicated context for password hashing.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_password_hash_input(password: str) -> str:
    """
    Bcrypt has a 72-byte limit. To handle passwords longer than 72 bytes
    without silent truncation, we hash the password with SHA-256 first.
    This is a professional standard approach for using bcrypt with long passwords.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt after pre-hashing with SHA-256."""
    return pwd_context.hash(_get_password_hash_input(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    # Check if the hash is in the old format (directly bcrypt'ed or truncated)
    # Most bcrypt hashes start with $2a$, $2b$, or $2y$.
    # If the verification fails with the SHA-256 pre-hash, we try verifying directly
    # to support legacy passwords if they were migrated or seeded previously.
    
    # Try the professional (SHA-256 + Bcrypt) verification first
    try:
        if pwd_context.verify(_get_password_hash_input(plain_password), hashed_password):
            return True
    except Exception:
        pass

    # Fallback for legacy passwords (direct bcrypt or 72-byte truncated)
    try:
        # We try both the full password and the 72-byte truncated one as the old code did
        if pwd_context.verify(plain_password, hashed_password):
            return True
        if pwd_context.verify(plain_password[:72], hashed_password):
            return True
    except Exception:
        pass
        
    return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
