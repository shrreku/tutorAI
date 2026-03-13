"""Credits repository — account, ledger, and grant operations.

All balance mutations go through the append-only ledger.  The ``balance``
column on ``CreditAccount`` is a **cached projection** that must always
equal ``SUM(delta)`` over all ledger entries for that account.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credits import (
    CreditAccount,
    CreditGrant,
    CreditLedgerEntry,
    ModelMultiplier,
)

logger = logging.getLogger(__name__)


class CreditAccountRepository:
    """Manages credit accounts and the append-only ledger."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Account operations
    # ------------------------------------------------------------------

    async def get_or_create_account(self, user_id: uuid.UUID) -> CreditAccount:
        """Return existing account or create a new one for *user_id*."""
        result = await self.db.execute(
            select(CreditAccount).where(CreditAccount.user_id == user_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = CreditAccount(user_id=user_id, balance=0)
            self.db.add(account)
            await self.db.flush()
        return account

    async def get_account(self, user_id: uuid.UUID) -> Optional[CreditAccount]:
        result = await self.db.execute(
            select(CreditAccount).where(CreditAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_balance(self, user_id: uuid.UUID) -> int:
        account = await self.get_account(user_id)
        return account.balance if account else 0

    # ------------------------------------------------------------------
    # Ledger operations (append-only)
    # ------------------------------------------------------------------

    async def _append_entry(
        self,
        account: CreditAccount,
        entry_type: str,
        delta: int,
        *,
        idempotency_key: Optional[str] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> CreditLedgerEntry:
        """Append an entry to the ledger and update cached balance."""
        # Idempotency guard
        if idempotency_key:
            existing = await self.db.execute(
                select(CreditLedgerEntry).where(
                    CreditLedgerEntry.idempotency_key == idempotency_key
                )
            )
            found = existing.scalar_one_or_none()
            if found:
                logger.info(
                    "Idempotent ledger entry already exists: %s", idempotency_key
                )
                return found

        new_balance = account.balance + delta
        entry = CreditLedgerEntry(
            account_id=account.id,
            entry_type=entry_type,
            delta=delta,
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            metadata_=metadata,
        )
        account.balance = new_balance
        if delta > 0:
            account.lifetime_granted += delta
        elif delta < 0:
            account.lifetime_used += abs(delta)

        self.db.add(entry)
        self.db.add(account)
        await self.db.flush()
        return entry

    # ------------------------------------------------------------------
    # Grant operations
    # ------------------------------------------------------------------

    async def issue_grant(
        self,
        user_id: uuid.UUID,
        amount: int,
        source: str = "monthly_grant",
        memo: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict] = None,
    ) -> CreditGrant:
        """Issue a credit grant and record it in the ledger."""
        account = await self.get_or_create_account(user_id)

        grant = CreditGrant(
            account_id=account.id,
            amount=amount,
            remaining=amount,
            source=source,
            memo=memo,
            expires_at=expires_at,
        )
        self.db.add(grant)
        await self.db.flush()

        await self._append_entry(
            account,
            "grant",
            amount,
            idempotency_key=f"grant:{grant.id}",
            reference_type="grant",
            reference_id=str(grant.id),
            metadata={"source": source, "memo": memo, **(metadata or {})},
        )
        return grant

    async def has_grant(
        self,
        user_id: uuid.UUID,
        *,
        source: Optional[str] = None,
        memo: Optional[str] = None,
    ) -> bool:
        """Return whether a matching grant already exists for the user."""
        account = await self.get_account(user_id)
        if account is None:
            return False

        query = select(CreditGrant.id).where(CreditGrant.account_id == account.id)
        if source is not None:
            query = query.where(CreditGrant.source == source)
        if memo is not None:
            query = query.where(CreditGrant.memo == memo)

        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Reserve / Debit / Release flow
    # ------------------------------------------------------------------

    async def reserve_credits(
        self,
        user_id: uuid.UUID,
        estimated_credits: int,
        reference_type: str = "turn",
        reference_id: Optional[str] = None,
    ) -> Optional[CreditLedgerEntry]:
        """Reserve credits for an in-progress operation.

        Returns None if insufficient balance.
        """
        account = await self.get_or_create_account(user_id)
        if account.balance < estimated_credits:
            return None

        return await self._append_entry(
            account,
            "reserve",
            -estimated_credits,
            idempotency_key=f"reserve:{reference_type}:{reference_id}"
            if reference_id
            else None,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    async def finalize_debit(
        self,
        user_id: uuid.UUID,
        actual_credits: int,
        reserved_credits: int,
        reference_type: str = "turn",
        reference_id: Optional[str] = None,
    ) -> CreditLedgerEntry:
        """Finalize a reservation into an actual debit.

        If actual < reserved, the difference is released back.
        If actual > reserved, additional credits are debited.
        """
        account = await self.get_or_create_account(user_id)
        diff = actual_credits - reserved_credits

        if diff < 0:
            # Release over-reservation
            await self._append_entry(
                account,
                "release",
                abs(diff),
                idempotency_key=f"release:{reference_type}:{reference_id}"
                if reference_id
                else None,
                reference_type=reference_type,
                reference_id=reference_id,
                metadata={"reserved": reserved_credits, "actual": actual_credits},
            )
        elif diff > 0:
            # Debit additional
            await self._append_entry(
                account,
                "debit",
                -diff,
                idempotency_key=f"debit_extra:{reference_type}:{reference_id}"
                if reference_id
                else None,
                reference_type=reference_type,
                reference_id=reference_id,
                metadata={"reserved": reserved_credits, "actual": actual_credits},
            )

        # Final debit record (the canonical cost record)
        return await self._append_entry(
            account,
            "debit",
            0,  # balance already adjusted via reserve/release
            idempotency_key=f"debit:{reference_type}:{reference_id}"
            if reference_id
            else None,
            reference_type=reference_type,
            reference_id=reference_id,
            metadata={
                "reserved": reserved_credits,
                "actual": actual_credits,
                "model_info": None,
            },
        )

    async def release_reservation(
        self,
        user_id: uuid.UUID,
        reserved_credits: int,
        reference_type: str = "turn",
        reference_id: Optional[str] = None,
    ) -> CreditLedgerEntry:
        """Release a full reservation (operation cancelled)."""
        account = await self.get_or_create_account(user_id)
        return await self._append_entry(
            account,
            "release",
            reserved_credits,
            idempotency_key=f"release_full:{reference_type}:{reference_id}"
            if reference_id
            else None,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def get_recent_ledger(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[CreditLedgerEntry]:
        """Get recent ledger entries for a user."""
        account = await self.get_account(user_id)
        if not account:
            return []
        result = await self.db.execute(
            select(CreditLedgerEntry)
            .where(CreditLedgerEntry.account_id == account.id)
            .order_by(CreditLedgerEntry.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def reconcile_balance(self, user_id: uuid.UUID) -> int:
        """Recompute balance from ledger and update cached balance.

        Returns the reconciled balance.
        """
        account = await self.get_account(user_id)
        if not account:
            return 0

        result = await self.db.execute(
            select(func.sum(CreditLedgerEntry.delta)).where(
                CreditLedgerEntry.account_id == account.id
            )
        )
        computed = result.scalar_one_or_none() or 0
        account.balance = computed
        self.db.add(account)
        await self.db.flush()
        return computed

    # ------------------------------------------------------------------
    # Model multiplier lookup
    # ------------------------------------------------------------------

    async def get_model_multiplier(self, model_id: str) -> Optional[ModelMultiplier]:
        result = await self.db.execute(
            select(ModelMultiplier).where(
                ModelMultiplier.model_id == model_id,
                ModelMultiplier.is_active,
            )
        )
        return result.scalar_one_or_none()

    async def compute_credits(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        uses_ocr: bool = False,
        uses_web_search: bool = False,
    ) -> int:
        """Compute credit cost for a given model + token usage."""
        from app.config import settings

        multiplier = await self.get_model_multiplier(model_id)
        input_mult = (
            multiplier.input_multiplier
            if multiplier
            else settings.CREDITS_INPUT_TOKEN_MULTIPLIER
        )
        output_mult = (
            multiplier.output_multiplier
            if multiplier
            else settings.CREDITS_OUTPUT_TOKEN_MULTIPLIER
        )

        cost = int(round(prompt_tokens * input_mult + completion_tokens * output_mult))
        if uses_ocr:
            cost += settings.CREDITS_OCR_SURCHARGE
        if uses_web_search:
            cost += settings.CREDITS_WEB_SEARCH_SURCHARGE
        return cost
