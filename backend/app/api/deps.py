"""
Shared FastAPI dependencies for authentication, rate-limiting, and BYOK.

When AUTH_ENABLED=false (local dev), all endpoints use a default user
and no token is required.  When AUTH_ENABLED=true (hosted/production),
a valid JWT Bearer token is mandatory on protected routes.
"""
import logging
import time
import uuid
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.repositories.session_repo import UserProfileRepository
from app.models.session import UserProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, *, expires_delta: Optional[timedelta] = None) -> str:
    """Issue a signed JWT for *user_id*."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.AUTH_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode & verify a JWT.  Raises on invalid/expired tokens."""
    return jwt.decode(token, settings.AUTH_SECRET_KEY, algorithms=[settings.AUTH_ALGORITHM])


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Resolve the current user.

    * AUTH_ENABLED=false  → returns (or creates) the default local user.
    * AUTH_ENABLED=true   → requires a valid JWT Bearer token; returns
      the matching UserProfile, creating one on first login.
    """
    user_repo = UserProfileRepository(db)

    if not settings.AUTH_ENABLED:
        return await user_repo.get_or_create_default()

    # --- Auth is enabled: extract and validate JWT ---
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_sub: str = payload.get("sub", "")
        if not user_sub:
            raise JWTError("Missing subject")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Lookup or auto-create profile for this external identity
    user = await user_repo.get_by_external_id(user_sub)
    if user is None:
        user = UserProfile(external_id=user_sub, display_name=user_sub)
        user = await user_repo.create(user)
    return user


async def require_auth(
    user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """Alias that makes intent explicit — protected endpoints use this."""
    return user


async def require_admin(
    user: UserProfile = Depends(require_auth),
) -> UserProfile:
    """Require an authenticated admin identity for privileged endpoints."""
    if not settings.AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin endpoint unavailable when auth is disabled",
        )

    allowed = {
        token.strip()
        for token in settings.ADMIN_EXTERNAL_IDS.split(",")
        if token.strip()
    }
    if not allowed or not user.external_id or user.external_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    return user


# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------


async def verify_session_owner(
    session_id: uuid.UUID,
    user: UserProfile,
    db: AsyncSession,
) -> None:
    """Raise 403 if *user* does not own the session (when auth is enabled)."""
    if not settings.AUTH_ENABLED:
        return  # ownership check unnecessary in local dev

    from app.db.repositories.session_repo import SessionRepository

    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


# ---------------------------------------------------------------------------
# Rate-limiting (simple in-memory, per-user)
# ---------------------------------------------------------------------------

_rate_limit_store: dict[str, list[float]] = {}
_rate_limit_redis: Optional[aioredis.Redis] = None
_rate_limit_redis_disabled_until: float = 0.0
_auth_rate_limit_store: dict[str, list[float]] = {}


async def _get_rate_limit_redis() -> Optional[aioredis.Redis]:
    """Return shared Redis client for distributed rate limiting."""
    global _rate_limit_redis
    global _rate_limit_redis_disabled_until

    if not settings.REDIS_URL:
        return None

    if time.time() < _rate_limit_redis_disabled_until:
        return None

    if _rate_limit_redis is None:
        _rate_limit_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    return _rate_limit_redis


async def check_rate_limit(user: UserProfile = Depends(get_current_user)) -> UserProfile:
    """Basic per-user request rate-limiter.  Returns the user on success."""
    if not settings.RATE_LIMIT_ENABLED:
        return user

    key = user.external_id or str(user.id)
    now = datetime.now(timezone.utc).timestamp()
    window = 60.0  # 1-minute window
    max_requests = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

    redis_client = await _get_rate_limit_redis()
    if redis_client is not None:
        try:
            bucket = int(now // window)
            redis_key = f"ratelimit:user:{key}:{bucket}"
            pipe = redis_client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, int(window) + 5)
            current_count, _ = await pipe.execute()

            if int(current_count) > max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Try again later.",
                    headers={"Retry-After": "60"},
                )

            return user
        except HTTPException:
            raise
        except Exception as exc:
            global _rate_limit_redis
            global _rate_limit_redis_disabled_until
            _rate_limit_redis = None
            _rate_limit_redis_disabled_until = time.time() + 30
            logger.warning("Redis rate-limit backend unavailable, falling back to local limiter: %s", exc)

    timestamps = _rate_limit_store.get(key, [])
    timestamps = [t for t in timestamps if now - t < window]

    if len(timestamps) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": "60"},
        )

    timestamps.append(now)
    _rate_limit_store[key] = timestamps
    return user


async def check_auth_rate_limit(request: Request) -> None:
    """Rate limit public auth endpoints by client IP."""
    if not settings.RATE_LIMIT_ENABLED:
        return

    client_ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).timestamp()
    window = 60.0
    max_requests = settings.AUTH_RATE_LIMIT_REQUESTS_PER_MINUTE

    key = f"auth:{client_ip}"
    timestamps = _auth_rate_limit_store.get(key, [])
    timestamps = [t for t in timestamps if now - t < window]

    if len(timestamps) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": "60"},
        )

    timestamps.append(now)
    _auth_rate_limit_store[key] = timestamps


# ---------------------------------------------------------------------------
# BYOK (Bring Your Own Key) dependency
# ---------------------------------------------------------------------------


def get_byok_api_key(
    x_llm_api_key: Optional[str] = Header(default=None, alias="X-LLM-Api-Key"),
    x_llm_api_base_url: Optional[str] = Header(default=None, alias="X-LLM-Api-Base-Url"),
) -> dict:
    """Extract BYOK LLM credentials from request headers.

    Returns a dict with ``api_key`` and ``api_base_url`` (both may be None
    when BYOK is disabled or when the caller doesn't supply headers).
    """
    if not settings.BYOK_ENABLED:
        return {"api_key": None, "api_base_url": None}

    normalized_base_url: Optional[str] = None
    if x_llm_api_base_url:
        parsed = urlparse(x_llm_api_base_url.strip())
        if parsed.scheme not in {"http", "https"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-LLM-Api-Base-Url scheme",
            )
        if parsed.username or parsed.password or parsed.fragment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-LLM-Api-Base-Url format",
            )
        if not parsed.hostname:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-LLM-Api-Base-Url host",
            )

        host = parsed.hostname.strip().lower()
        if settings.BYOK_REQUIRE_HTTPS and parsed.scheme != "https":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-LLM-Api-Base-Url must use https",
            )

        if not settings.BYOK_ALLOW_PRIVATE_BASE_URLS:
            blocked_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
            if host in blocked_hosts or host.endswith(".local"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Private or local X-LLM-Api-Base-Url hosts are not allowed",
                )
            try:
                host_ip = ipaddress.ip_address(host)
            except ValueError:
                host_ip = None
            if host_ip and (
                host_ip.is_private
                or host_ip.is_loopback
                or host_ip.is_link_local
                or host_ip.is_multicast
                or host_ip.is_reserved
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Private or local X-LLM-Api-Base-Url IPs are not allowed",
                )

        normalized_base_url = parsed.geturl().rstrip("/")

    return {
        "api_key": x_llm_api_key,
        "api_base_url": normalized_base_url,
    }
