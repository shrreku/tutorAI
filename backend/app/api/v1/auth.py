"""
Public authentication endpoints — register & login.

These endpoints do NOT require an existing JWT.  They issue new tokens
after verifying credentials (login) or creating an account (register).

When ALPHA_ACCESS_ENABLED=True, /register requires either:
  - A valid invite_token (issued by admin after approving an access request), OR
  - A valid promo_code (from ALPHA_PROMO_CODES config).
Users first submit a request via /auth/request-access; admin approves via the
billing admin API which sends an email with a one-time registration link.
"""
import logging
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_auth_rate_limit, create_access_token, is_admin_user
from app.config import settings
from app.db.database import get_db
from app.db.repositories.session_repo import UserProfileRepository
from app.models.alpha import AlphaAccessRequest
from app.models.session import UserProfile
from app.services.credits.meter import CreditMeter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)
    consent_training: bool = Field(
        default=False,
        description="Opt-in to allow anonymised tutoring data for research",
    )
    invite_token: Optional[str] = Field(
        default=None,
        description="One-time invite token received via email (required when alpha access is enabled)",
    )
    promo_code: Optional[str] = Field(
        default=None,
        description="Promo / early-access code (alternative to invite_token)",
    )


class RequestAccessRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=128)
    promo_code: Optional[str] = Field(default=None, max_length=128)


class RequestAccessResponse(BaseModel):
    status: str  # "submitted" | "approved" (promo bypass)
    message: str


class AuthConfigResponse(BaseModel):
    alpha_access_enabled: bool
    app_base_url: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "AuthUserInfo"


class AuthUserInfo(BaseModel):
    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    consent_training_global: bool = False
    is_admin: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/config", response_model=AuthConfigResponse, status_code=status.HTTP_200_OK)
async def auth_config():
    """Return public auth/onboarding configuration for the frontend."""
    return AuthConfigResponse(
        alpha_access_enabled=settings.ALPHA_ACCESS_ENABLED,
        app_base_url=settings.APP_BASE_URL,
    )


@router.post("/request-access", response_model=RequestAccessResponse, status_code=status.HTTP_200_OK)
async def request_access(
    body: RequestAccessRequest,
    _: None = Depends(check_auth_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Submit an alpha access request.

    If a valid promo code is supplied the request is auto-approved and the
    caller can immediately proceed to /register with that promo code.
    Otherwise the request goes into the pending queue for admin review.
    Always returns 200 (no enumeration of existing requests).
    """
    # Check for valid promo code — bypass manual approval
    if body.promo_code:
        valid_promos = {c.strip() for c in settings.ALPHA_PROMO_CODES.split(",") if c.strip()}
        if body.promo_code in valid_promos:
            # Upsert / idempotent: if already exists, just tell them they're good
            result = await db.execute(
                select(AlphaAccessRequest).where(AlphaAccessRequest.email == str(body.email))
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                req = AlphaAccessRequest(
                    email=str(body.email),
                    display_name=body.display_name,
                    status="approved",
                    promo_code_used=body.promo_code,
                )
                db.add(req)
                await db.commit()
            return RequestAccessResponse(
                status="approved",
                message="Valid promo code accepted. Proceed to register with your promo code.",
            )

    # Queue request for admin review (idempotent)
    result = await db.execute(
        select(AlphaAccessRequest).where(AlphaAccessRequest.email == str(body.email))
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        req = AlphaAccessRequest(
            email=str(body.email),
            display_name=body.display_name,
            status="pending",
            promo_code_used=body.promo_code if body.promo_code else None,
        )
        db.add(req)
        await db.commit()

    return RequestAccessResponse(
        status="submitted",
        message="Your request has been received. We'll email you when your access is approved.",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    _: None = Depends(check_auth_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account and return a JWT.

    When ALPHA_ACCESS_ENABLED is True, the request must include either:
    - invite_token: a one-time token received via email after admin approval, OR
    - promo_code: a valid code from ALPHA_PROMO_CODES config.
    """
    # ---------------------------------------------------------------------------
    # Alpha access gate
    # ---------------------------------------------------------------------------
    alpha_request: Optional[AlphaAccessRequest] = None

    if settings.ALPHA_ACCESS_ENABLED:
        if body.invite_token:
            result = await db.execute(
                select(AlphaAccessRequest).where(
                    AlphaAccessRequest.invite_token == body.invite_token,
                    AlphaAccessRequest.status == "approved",
                    AlphaAccessRequest.invite_used.is_(False),
                )
            )
            alpha_request = result.scalar_one_or_none()
            if alpha_request is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or already-used invite token",
                )
            # Ensure email matches the invite
            if alpha_request.email.lower() != str(body.email).lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This invite token was issued for a different email address",
                )
        elif body.promo_code:
            valid_promos = {c.strip() for c in settings.ALPHA_PROMO_CODES.split(",") if c.strip()}
            if body.promo_code not in valid_promos:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid promo code",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration requires an invite token or promo code during alpha access",
            )

    # ---------------------------------------------------------------------------
    # Account creation
    # ---------------------------------------------------------------------------
    repo = UserProfileRepository(db)

    existing = await repo.get_by_email(body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    password_hash = _hash_password(body.password)

    user = UserProfile(
        external_id=body.email,
        email=body.email,
        display_name=body.display_name,
        password_hash=password_hash,
        preferences={
            "consent_training_global": body.consent_training,
            "consent_preference_set": True,
        },
    )
    user = await repo.create(user)

    # Mark invite used (prevents replay)
    if alpha_request is not None:
        alpha_request.invite_used = True
        await db.commit()

    meter = CreditMeter(db)
    await meter.issue_signup_grant_if_missing(user.id)

    token = create_access_token(user.external_id or str(user.id))

    return AuthResponse(
        access_token=token,
        user=AuthUserInfo(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            consent_training_global=body.consent_training,
            is_admin=is_admin_user(user),
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    _: None = Depends(check_auth_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password and receive a JWT."""
    repo = UserProfileRepository(db)

    user = await repo.get_by_email(body.email)
    if user is None or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.external_id or str(user.id))

    consent = (user.preferences or {}).get("consent_training_global", False)

    return AuthResponse(
        access_token=token,
        user=AuthUserInfo(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            consent_training_global=consent,
            is_admin=is_admin_user(user),
        ),
    )
