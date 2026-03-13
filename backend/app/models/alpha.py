"""Alpha access request model — tracks pre-registration access requests."""

import secrets
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class AlphaAccessRequest(Base, UUIDMixin, TimestampMixin):
    """A request for early access submitted before account creation.

    Status flow:  pending → approved (invite_token generated, email sent)
                  pending → rejected
    """

    __tablename__ = "alpha_access_request"

    email: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)

    # pending | approved | rejected
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )

    # One-time registration token; generated when admin approves the request
    invite_token: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )

    # Set to True after the user successfully registers with this token
    invite_used: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Optional promo code that was used at request time (bypasses manual approval)
    promo_code_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Free-text notes from admin (reason for rejection, etc.)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @staticmethod
    def generate_token() -> str:
        """Generate a URL-safe 48-byte random invite token."""
        return secrets.token_urlsafe(48)
