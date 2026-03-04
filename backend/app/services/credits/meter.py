"""Credit metering service — converts token usage into credit charges.

This module provides the metering bridge between the turn pipeline / ingestion
pipeline and the credits ledger.  It implements the reserve-then-finalize
pattern described in the L009 ticket.
"""

import logging
import uuid
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

    async def ensure_account(self, user_id: uuid.UUID) -> None:
        """Lazily create a credit account and issue the default monthly grant
        if the user doesn't have one yet."""
        if not settings.CREDITS_ENABLED:
            return
        account = await self.repo.get_account(user_id)
        if account is None:
            await self.repo.issue_grant(
                user_id,
                amount=settings.CREDITS_DEFAULT_MONTHLY_GRANT,
                source="monthly_grant",
                memo="Initial monthly research grant",
            )
            logger.info("Issued default grant of %d to user %s", settings.CREDITS_DEFAULT_MONTHLY_GRANT, user_id)

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
