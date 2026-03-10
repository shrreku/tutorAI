"""Credit metering service — converts token usage into credit charges.

This module provides the metering bridge between the turn pipeline / ingestion
pipeline and the credits ledger.  It implements the reserve-then-finalize
pattern described in the L009 ticket.
"""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.credits_repo import CreditAccountRepository

logger = logging.getLogger(__name__)


class CreditMeter:
    """Stateless metering helper — call from turn or ingestion pipelines."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CreditAccountRepository(db)

    @staticmethod
    def current_grant_period_key(now: datetime | None = None) -> str:
        current = now or datetime.now(timezone.utc)
        return f"{current.year:04d}-{current.month:02d}"

    @staticmethod
    def default_signup_grant_memo(now: datetime | None = None) -> str:
        return f"Initial research grant at signup ({CreditMeter.current_grant_period_key(now)})"

    async def ensure_account(self, user_id: uuid.UUID) -> None:
        """Lazily create a credit account and issue the default monthly grant
        if the user doesn't have one yet."""
        if not settings.CREDITS_ENABLED:
            return
        account = await self.repo.get_account(user_id)
        if account is None:
            await self.issue_signup_grant_if_missing(user_id)

    async def issue_signup_grant_if_missing(self, user_id: uuid.UUID) -> bool:
        """Create the user's initial research grant exactly once."""
        if not settings.CREDITS_ENABLED:
            return False

        memo = self.default_signup_grant_memo()
        if await self.repo.has_grant(user_id, source="signup_grant", memo=memo):
            return False

        await self.repo.issue_grant(
            user_id,
            amount=settings.CREDITS_DEFAULT_MONTHLY_GRANT,
            source="signup_grant",
            memo=memo,
            metadata={"grant_period": self.current_grant_period_key()},
        )
        logger.info(
            "Issued signup grant of %d to user %s",
            settings.CREDITS_DEFAULT_MONTHLY_GRANT,
            user_id,
        )
        return True

    async def check_sufficient_balance(
        self, user_id: uuid.UUID, estimated_credits: int
    ) -> bool:
        """Return True if the user has enough credits (or credits are disabled)."""
        if not settings.CREDITS_ENABLED:
            return True
        balance = await self.repo.get_balance(user_id)
        return balance >= estimated_credits

    async def reserve_for_turn(
        self,
        user_id: uuid.UUID,
        turn_id: str,
        estimated_credits: int,
    ) -> Optional[int]:
        """Reserve credits before executing a turn.

        Returns the reserved amount, or None if insufficient balance.
        Returns 0 when credits are disabled.
        """
        if not settings.CREDITS_ENABLED:
            return 0
        await self.ensure_account(user_id)
        entry = await self.repo.reserve_credits(
            user_id, estimated_credits, reference_type="turn", reference_id=turn_id
        )
        if entry is None:
            return None
        return estimated_credits

    async def finalize_turn(
        self,
        user_id: uuid.UUID,
        turn_id: str,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        reserved_credits: int,
        *,
        uses_ocr: bool = False,
    ) -> int:
        """Finalize the actual credit charge after a turn completes.

        Returns the actual credits charged.
        """
        if not settings.CREDITS_ENABLED:
            return 0
        actual = await self.repo.compute_credits(
            model_id, prompt_tokens, completion_tokens, uses_ocr=uses_ocr
        )
        await self.repo.finalize_debit(
            user_id,
            actual_credits=actual,
            reserved_credits=reserved_credits,
            reference_type="turn",
            reference_id=turn_id,
        )
        logger.info(
            "Turn %s cost %d credits (reserved %d) for model %s",
            turn_id, actual, reserved_credits, model_id,
        )
        return actual

    async def release_turn(
        self,
        user_id: uuid.UUID,
        turn_id: str,
        reserved_credits: int,
    ) -> None:
        """Release a reservation when a turn fails."""
        if not settings.CREDITS_ENABLED or reserved_credits <= 0:
            return
        await self.repo.release_reservation(
            user_id, reserved_credits, reference_type="turn", reference_id=turn_id
        )

    async def charge_ingestion(
        self,
        user_id: uuid.UUID,
        job_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        model_id: str,
        *,
        uses_ocr: bool = False,
    ) -> int:
        """Direct debit for ingestion (no reservation needed since it's async)."""
        if not settings.CREDITS_ENABLED:
            return 0
        await self.ensure_account(user_id)
        actual = await self.repo.compute_credits(
            model_id, prompt_tokens, completion_tokens, uses_ocr=uses_ocr
        )
        account = await self.repo.get_or_create_account(user_id)
        await self.repo._append_entry(
            account,
            "debit",
            -actual,
            idempotency_key=f"ingest:{job_id}:{model_id}",
            reference_type="ingestion",
            reference_id=job_id,
            metadata={
                "model_id": model_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )
        return actual

    def estimate_ingestion_credits(
        self,
        *,
        file_size_bytes: int,
        filename: str,
        processing_profile: str = "core_only",
    ) -> int:
        """Estimate ingestion credits before a job is accepted.

        The estimate is intentionally conservative and based on file size,
        probable OCR risk for PDFs, and the selected preparation profile.
        """
        del processing_profile

        size_mb = max(1, math.ceil(max(file_size_bytes, 1) / (1024 * 1024)))
        estimate = settings.CREDITS_INGESTION_BASE_ESTIMATE + size_mb * settings.CREDITS_INGESTION_PER_MB
        if filename.lower().endswith(".pdf"):
            estimate += settings.CREDITS_INGESTION_PDF_SURCHARGE
        return estimate

    async def reserve_for_ingestion(
        self,
        user_id: uuid.UUID,
        job_id: str,
        estimated_credits: int,
    ) -> Optional[int]:
        """Reserve credits before accepting an ingestion job."""
        if not settings.CREDITS_ENABLED:
            return 0
        await self.ensure_account(user_id)
        entry = await self.repo.reserve_credits(
            user_id,
            estimated_credits,
            reference_type="ingestion",
            reference_id=job_id,
        )
        if entry is None:
            return None
        logger.info("Reserved %d credits for ingestion job %s", estimated_credits, job_id)
        return estimated_credits

    async def finalize_ingestion(
        self,
        user_id: uuid.UUID,
        job_id: str,
        actual_credits: int,
        reserved_credits: int,
    ) -> int:
        """Finalize an ingestion reservation when the worker completes."""
        if not settings.CREDITS_ENABLED:
            return 0
        await self.repo.finalize_debit(
            user_id,
            actual_credits=actual_credits,
            reserved_credits=reserved_credits,
            reference_type="ingestion",
            reference_id=job_id,
        )
        logger.info(
            "Finalized ingestion job %s cost %d credits (reserved %d)",
            job_id,
            actual_credits,
            reserved_credits,
        )
        return actual_credits

    async def release_ingestion(
        self,
        user_id: uuid.UUID,
        job_id: str,
        reserved_credits: int,
    ) -> None:
        """Release a reserved ingestion amount on failure/cancellation."""
        if not settings.CREDITS_ENABLED or reserved_credits <= 0:
            return
        await self.repo.release_reservation(
            user_id,
            reserved_credits,
            reference_type="ingestion",
            reference_id=job_id,
        )
        logger.info("Released %d reserved credits for ingestion job %s", reserved_credits, job_id)
