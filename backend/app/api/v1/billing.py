from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth, require_admin
from app.config import settings
from app.db.database import get_db
from app.db.repositories.credits_repo import CreditAccountRepository
from app.models.session import UserProfile
from app.schemas.api import CreditEstimateRequest, CreditEstimateResponse

router = APIRouter(prefix="/billing", tags=["billing"])


# ---- Additional schemas for billing endpoints ----

class BalanceResponse(BaseModel):
    credits_enabled: bool
    balance: int = 0
    lifetime_granted: int = 0
    lifetime_used: int = 0
    plan_tier: str = "free_research"
    daily_limit: int = 0
    monthly_limit: int = 0
    soft_limit_pct: float = 0.8


class LedgerEntryResponse(BaseModel):
    id: str
    entry_type: str
    delta: int
    balance_after: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    created_at: str


class UsageHistoryResponse(BaseModel):
    credits_enabled: bool
    entries: list[LedgerEntryResponse] = []


class AdminGrantRequest(BaseModel):
    user_id: str
    amount: int = Field(gt=0)
    source: str = "admin_topup"
    memo: Optional[str] = None


class AdminGrantResponse(BaseModel):
    grant_id: str
    user_id: str
    amount: int
    new_balance: int


# ---- Endpoints ----

@router.post("/estimate", response_model=CreditEstimateResponse)
async def estimate_credits(
    request: CreditEstimateRequest,
    user: UserProfile = Depends(require_auth),
):
    """Estimate token-to-credit charge using configured multipliers."""
    del user

    input_component = int(round(request.prompt_tokens * settings.CREDITS_INPUT_TOKEN_MULTIPLIER))
    output_component = int(round(request.completion_tokens * settings.CREDITS_OUTPUT_TOKEN_MULTIPLIER))
    ocr_surcharge = settings.CREDITS_OCR_SURCHARGE if request.uses_ocr else 0
    web_search_surcharge = settings.CREDITS_WEB_SEARCH_SURCHARGE if request.uses_web_search else 0

    estimated_credits = input_component + output_component + ocr_surcharge + web_search_surcharge

    return CreditEstimateResponse(
        credits_enabled=settings.CREDITS_ENABLED,
        estimated_credits=estimated_credits,
        input_component=input_component,
        output_component=output_component,
        ocr_surcharge=ocr_surcharge,
        web_search_surcharge=web_search_surcharge,
    )


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get current credit balance and plan info."""
    if not settings.CREDITS_ENABLED:
        return BalanceResponse(credits_enabled=False)

    repo = CreditAccountRepository(db)
    account = await repo.get_account(user.id)
    if not account:
        return BalanceResponse(
            credits_enabled=True,
            daily_limit=settings.CREDITS_DAILY_LIMIT,
            monthly_limit=settings.CREDITS_MONTHLY_LIMIT,
            soft_limit_pct=settings.CREDITS_SOFT_LIMIT_PCT,
        )

    return BalanceResponse(
        credits_enabled=True,
        balance=account.balance,
        lifetime_granted=account.lifetime_granted,
        lifetime_used=account.lifetime_used,
        plan_tier=account.plan_tier,
        daily_limit=settings.CREDITS_DAILY_LIMIT,
        monthly_limit=settings.CREDITS_MONTHLY_LIMIT,
        soft_limit_pct=settings.CREDITS_SOFT_LIMIT_PCT,
    )


@router.get("/usage", response_model=UsageHistoryResponse)
async def get_usage_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get recent credit usage ledger entries."""
    if not settings.CREDITS_ENABLED:
        return UsageHistoryResponse(credits_enabled=False)

    repo = CreditAccountRepository(db)
    entries = await repo.get_recent_ledger(user.id, limit=limit)

    return UsageHistoryResponse(
        credits_enabled=True,
        entries=[
            LedgerEntryResponse(
                id=str(e.id),
                entry_type=e.entry_type,
                delta=e.delta,
                balance_after=e.balance_after,
                reference_type=e.reference_type,
                reference_id=e.reference_id,
                created_at=e.created_at.isoformat() if e.created_at else "",
            )
            for e in entries
        ],
    )


@router.post("/admin/grant", response_model=AdminGrantResponse)
async def admin_grant(
    request: AdminGrantRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin endpoint: manually grant credits to a user.

    This endpoint is restricted to configured admin identities.
    """
    import uuid as _uuid

    repo = CreditAccountRepository(db)
    target_user_id = _uuid.UUID(request.user_id)

    grant = await repo.issue_grant(
        target_user_id,
        amount=request.amount,
        source=request.source,
        memo=request.memo,
    )
    await db.commit()

    account = await repo.get_account(target_user_id)

    return AdminGrantResponse(
        grant_id=str(grant.id),
        user_id=request.user_id,
        amount=request.amount,
        new_balance=account.balance if account else 0,
    )
