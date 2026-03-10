"""
Public authentication endpoints — register & login.

These endpoints do NOT require an existing JWT.  They issue new tokens
after verifying credentials (login) or creating an account (register).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt

from app.config import settings
from app.db.database import get_db
from app.db.repositories.session_repo import UserProfileRepository
from app.models.session import UserProfile
from app.api.deps import check_auth_rate_limit, create_access_token, is_admin_user
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


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    _: None = Depends(check_auth_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account and return a JWT."""
    repo = UserProfileRepository(db)

    existing = await repo.get_by_email(body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    password_hash = _hash_password(body.password)

    user = UserProfile(
        external_id=body.email,  # email doubles as the external identity
        email=body.email,
        display_name=body.display_name,
        password_hash=password_hash,
        preferences={
            "consent_training_global": body.consent_training,
            "consent_preference_set": True,
        },
    )
    user = await repo.create(user)

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
