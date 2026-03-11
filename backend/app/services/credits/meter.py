"""Credit metering service — converts token usage into credit charges.

This module provides the metering bridge between the turn pipeline / ingestion
pipeline and the credits ledger.  It implements the reserve-then-finalize
pattern described in the L009 ticket, extended with operation-based metering
from the CM ticket series.
"""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.credits_repo import CreditAccountRepository
from app.db.repositories.metering_repo import MeteringRepository
from app.services.telemetry.billing_events import emit_billing_event, emit_cost_drift, emit_estimation_quality

if TYPE_CHECKING:
    from app.models.credits import BillingOperation, BillingUsageLine

logger = logging.getLogger(__name__)


class CreditMeter:
    """Stateless metering helper — call from turn or ingestion pipelines."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CreditAccountRepository(db)
        self.metering_repo = MeteringRepository(db)

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
            amount=settings.CREDITS_SIGNUP_GRANT,
            source="signup_grant",
            memo=memo,
            metadata={"grant_period": self.current_grant_period_key()},
        )
        logger.info(
            "Issued signup grant of %d to user %s",
            settings.CREDITS_SIGNUP_GRANT,
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

    async def estimate_turn_credits(
        self,
        model_id: str,
        *,
        prompt_tokens: int = 250,
        completion_tokens: int = 150,
        uses_ocr: bool = False,
        uses_web_search: bool = False,
    ) -> int:
        """Estimate a conservative turn reservation using the same pricing path as finalization."""
        estimate = await self.repo.compute_credits(
            model_id,
            prompt_tokens,
            completion_tokens,
            uses_ocr=uses_ocr,
            uses_web_search=uses_web_search,
        )
        return min(settings.CREDITS_TURN_MAX_COST, max(estimate, 250))

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

    # ------------------------------------------------------------------
    # Operation-based metering (CM-004)
    # ------------------------------------------------------------------

    async def create_operation(
        self,
        user_id: uuid.UUID,
        operation_type: str,
        *,
        resource_id: Optional[str] = None,
        session_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        selected_model_id: Optional[str] = None,
        estimate_credits_low: Optional[int] = None,
        estimate_credits_high: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> "BillingOperation":
        """Create a new billing operation."""
        if not settings.OPERATION_METERING_ENABLED:
            from app.models.credits import BillingOperation
            # Return a transient object so callers don't need to branch
            return BillingOperation(
                id=uuid.uuid4(), user_id=user_id, operation_type=operation_type,
                status="disabled",
            )
        return await self.metering_repo.create_operation(
            user_id, operation_type,
            resource_id=resource_id, session_id=session_id, artifact_id=artifact_id,
            selected_model_id=selected_model_id,
            estimate_credits_low=estimate_credits_low,
            estimate_credits_high=estimate_credits_high,
            metadata=metadata,
        )

    async def reserve_operation(
        self,
        user_id: uuid.UUID,
        operation_id: uuid.UUID,
        estimated_credits: int,
        reference_id: str,
        reference_type: str = "operation",
    ) -> Optional[int]:
        """Reserve credits for an operation. Returns None if insufficient."""
        if not settings.CREDITS_ENABLED:
            return 0
        await self.ensure_account(user_id)
        entry = await self.repo.reserve_credits(
            user_id, estimated_credits,
            reference_type=reference_type, reference_id=reference_id,
        )
        if entry is None:
            return None
        if settings.OPERATION_METERING_ENABLED:
            await self.metering_repo.update_operation_status(
                operation_id, "reserved", reserved_credits=estimated_credits,
            )
        return estimated_credits

    async def append_usage_line(
        self,
        operation_id: uuid.UUID,
        task_type: str,
        model_id: str,
        *,
        provider_name: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        tool_units: int = 0,
    ) -> Optional["BillingUsageLine"]:
        """Record a usage line for an operation, computing raw USD from pricing."""
        if not settings.OPERATION_METERING_ENABLED:
            return None

        raw_usd = await self._compute_raw_usd(
            model_id, input_tokens, output_tokens,
            cache_write_tokens, cache_read_tokens, tool_units,
        )
        return await self.metering_repo.append_usage_line(
            operation_id, task_type, model_id,
            provider_name=provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            tool_units=tool_units,
            raw_usd=raw_usd,
        )

    async def finalize_operation(
        self,
        user_id: uuid.UUID,
        operation_id: uuid.UUID,
        reserved_credits: int,
        reference_id: str,
        reference_type: str = "operation",
    ) -> int:
        """Finalize an operation from aggregated usage lines. Returns final credits."""
        if not settings.CREDITS_ENABLED:
            return 0

        lines = await self.metering_repo.get_operation_usage_lines(operation_id)
        total_usd = sum(line.raw_usd for line in lines) if lines else 0.0

        # Determine model class floor
        model_class_floor = await self._resolve_model_class_floor(lines)
        final_credits = self._usd_to_credits(total_usd, model_class_floor)

        # Finalize through the ledger
        await self.repo.finalize_debit(
            user_id,
            actual_credits=final_credits,
            reserved_credits=reserved_credits,
            reference_type=reference_type,
            reference_id=reference_id,
        )

        if settings.OPERATION_METERING_ENABLED:
            await self.metering_repo.update_operation_status(
                operation_id, "finalized",
                final_credits=final_credits,
                final_usd=total_usd,
            )

        logger.info(
            "Finalized operation %s: %d credits ($%.6f), reserved was %d",
            operation_id, final_credits, total_usd, reserved_credits,
        )
        emit_billing_event(
            "billing.operation.finalized",
            user_id=str(user_id),
            operation_id=str(operation_id),
            metadata={"final_credits": final_credits, "final_usd": total_usd, "reference_type": reference_type},
        )

        # CM-018: Emit cost drift metric when estimate was provided
        if reserved_credits > 0:
            emit_cost_drift(
                user_id=str(user_id),
                operation_id=str(operation_id),
                operation_type=reference_type,
                estimated_credits=reserved_credits,
                actual_credits=final_credits,
                model_id=model_class_floor or "unknown",
            )

        return final_credits

    async def release_operation(
        self,
        user_id: uuid.UUID,
        operation_id: uuid.UUID,
        reserved_credits: int,
        reference_id: str,
        reference_type: str = "operation",
    ) -> None:
        """Release an operation reservation on failure."""
        if not settings.CREDITS_ENABLED or reserved_credits <= 0:
            return
        await self.repo.release_reservation(
            user_id, reserved_credits,
            reference_type=reference_type, reference_id=reference_id,
        )
        if settings.OPERATION_METERING_ENABLED:
            await self.metering_repo.update_operation_status(
                operation_id, "released",
            )
        emit_billing_event(
            "billing.operation.released",
            user_id=str(user_id),
            operation_id=str(operation_id),
            metadata={"reserved_credits": reserved_credits, "reference_type": reference_type},
        )

    async def _compute_raw_usd(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        tool_units: int = 0,
    ) -> float:
        """Compute raw USD from model pricing table."""
        pricing = await self.metering_repo.get_model_pricing(model_id)
        if pricing is None:
            # Fallback: use old multiplier-based calc, convert to rough USD
            old_credits = await self.repo.compute_credits(model_id, input_tokens, output_tokens)
            return old_credits * settings.CREDITS_USD_PER_CREDIT

        raw = (
            input_tokens * pricing.input_usd_per_million / 1_000_000
            + output_tokens * pricing.output_usd_per_million / 1_000_000
        )
        if pricing.cache_write_usd_per_million and cache_write_tokens:
            raw += cache_write_tokens * pricing.cache_write_usd_per_million / 1_000_000
        if pricing.cache_read_usd_per_million and cache_read_tokens:
            raw += cache_read_tokens * pricing.cache_read_usd_per_million / 1_000_000
        if pricing.search_usd_per_unit and tool_units:
            raw += tool_units * pricing.search_usd_per_unit
        return raw

    def _get_model_class_floor(self, lines: list | None) -> str:
        """Get the highest model class observed across usage lines."""
        if not lines:
            return "economy"

        class_rank = {"economy": 1, "standard": 2, "premium_small": 3}
        highest_class = "economy"
        highest_rank = class_rank[highest_class]

        for line in lines:
            model_class = getattr(line, "model_class", None) or "economy"
            rank = class_rank.get(model_class, class_rank["economy"])
            if rank > highest_rank:
                highest_class = model_class
                highest_rank = rank

        return highest_class

    async def _resolve_model_class_floor(self, lines: list | None) -> str:
        """Resolve the highest model class using pricing data when available."""
        if not lines:
            return "economy"

        class_rank = {"economy": 1, "standard": 2, "premium_small": 3}
        highest_class = self._get_model_class_floor(lines)
        highest_rank = class_rank.get(highest_class, class_rank["economy"])

        for line in lines:
            pricing = await self.metering_repo.get_model_pricing(line.model_id)
            model_class = pricing.model_class if pricing and pricing.model_class else "economy"
            rank = class_rank.get(model_class, class_rank["economy"])
            if rank > highest_rank:
                highest_class = model_class
                highest_rank = rank

        return highest_class

    @staticmethod
    def _usd_to_credits(usd: float, model_class_floor: int | str = 50) -> int:
        """Convert USD to credits using the configured rate.

        1 credit = $0.008. Round to half-credit (50-unit) increments.
        Apply model-class floor.
        """
        floors = {"economy": 50, "standard": 100, "premium_small": 200}
        if isinstance(model_class_floor, str):
            floor_value = floors.get(model_class_floor, floors["economy"])
        else:
            floor_value = model_class_floor

        if usd <= 0:
            return floor_value
        raw_credits = usd / settings.CREDITS_USD_PER_CREDIT
        # Round to nearest 50 (half-credit)
        rounded = max(floor_value, int(math.ceil(raw_credits / 50) * 50))
        return rounded

    def estimate_ingestion_v2(
        self,
        *,
        file_size_bytes: int,
        filename: str,
        page_count_estimate: int = 0,
        token_count_estimate: int = 0,
        chunk_count_estimate: int = 0,
    ) -> dict:
        """V2 ingestion estimate with ranges (CM-008)."""
        size_mb = max(1, math.ceil(max(file_size_bytes, 1) / (1024 * 1024)))
        is_pdf = filename.lower().endswith(".pdf")

        # Token estimates
        if token_count_estimate <= 0:
            # Heuristic: ~500 tokens per KB for text, ~300 for PDF
            multiplier = 300 if is_pdf else 500
            token_count_estimate = int(file_size_bytes / 1024 * multiplier)

        if chunk_count_estimate <= 0:
            chunk_count_estimate = max(1, token_count_estimate // 500)

        if page_count_estimate <= 0 and is_pdf:
            page_count_estimate = max(1, file_size_bytes // 50_000)

        # Ontology tokens (full-content extraction)
        ontology_tokens_low = min(token_count_estimate, 50_000)
        ontology_tokens_high = min(token_count_estimate * 2, 200_000)
        ontology_output_low = 2000
        ontology_output_high = 8000

        # Enrichment tokens (per-chunk)
        enrich_input_low = chunk_count_estimate * 800
        enrich_input_high = chunk_count_estimate * 2000
        enrich_output_low = chunk_count_estimate * 200
        enrich_output_high = chunk_count_estimate * 600

        # USD estimates using economy pricing (ontology=standard, enrichment=economy)
        std_in = 0.10 / 1_000_000   # standard input per token
        std_out = 0.40 / 1_000_000
        eco_in = 0.015 / 1_000_000
        eco_out = 0.06 / 1_000_000

        usd_low = (
            ontology_tokens_low * std_in + ontology_output_low * std_out
            + enrich_input_low * eco_in + enrich_output_low * eco_out
        )
        usd_high = (
            ontology_tokens_high * std_in + ontology_output_high * std_out
            + enrich_input_high * eco_in + enrich_output_high * eco_out
        )

        credits_low = max(100, self._usd_to_credits(usd_low))
        credits_high = max(credits_low, self._usd_to_credits(usd_high))

        warnings = []
        if is_pdf and size_mb > 10:
            warnings.append("Large PDF — estimate range may be wider than usual")
        if token_count_estimate > 500_000:
            warnings.append("Very large document — processing may take longer")

        confidence = "medium" if token_count_estimate > 0 else "low"

        return {
            "estimated_credits_low": credits_low,
            "estimated_credits_high": credits_high,
            "estimated_usd_low": round(usd_low, 6),
            "estimated_usd_high": round(usd_high, 6),
            "page_count_estimate": page_count_estimate,
            "token_count_estimate": token_count_estimate,
            "chunk_count_estimate": chunk_count_estimate,
            "estimate_confidence": confidence,
            "confidence": confidence,
            "warnings": warnings,
        }
