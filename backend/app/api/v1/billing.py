import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    require_auth,
    require_admin,
    get_configured_admin_external_id,
    is_admin_user,
)
from app.config import settings
from app.db.database import get_db
from app.db.repositories.credits_repo import CreditAccountRepository
from app.models.alpha import AlphaAccessRequest
from app.models.credits import CreditAccount
from app.models.session import UserProfile
from app.schemas.api import CreditEstimateRequest, CreditEstimateResponse
from app.services.credits.meter import CreditMeter
from app.services.email import send_email, build_alpha_invite_email
from app.services.ingestion.page_allowance import PageAllowanceService

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)


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
    default_monthly_grant: int = 0


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
    amount: int = Field(gt=0, le=settings.ADMIN_CREDIT_GRANT_MAX)
    source: str = Field(default="admin_topup", pattern=r"^[a-z_]{3,32}$")
    memo: str = Field(min_length=3, max_length=280)


class AdminGrantResponse(BaseModel):
    grant_id: str
    user_id: str
    amount: int
    new_balance: int


class AdminPageAllowanceGrantRequest(BaseModel):
    user_id: str
    amount: int = Field(gt=0, le=settings.ADMIN_PAGE_ALLOWANCE_GRANT_MAX)
    memo: str = Field(min_length=3, max_length=280)


class AdminPageAllowanceGrantResponse(BaseModel):
    user_id: str
    amount: int
    new_limit: int
    remaining_pages: int


class AdminUserSummaryResponse(BaseModel):
    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    external_id: Optional[str] = None
    created_at: str
    balance: int = 0
    lifetime_granted: int = 0
    lifetime_used: int = 0
    is_admin: bool = False
    parse_page_limit: int = 0
    parse_page_used: int = 0
    parse_page_reserved: int = 0
    parse_page_remaining: int = 0


class AdminOverviewResponse(BaseModel):
    configured_admin_external_id: Optional[str] = None
    credits_enabled: bool
    default_monthly_grant: int = 0
    default_page_allowance: int = 0
    current_grant_period: str
    users: list[AdminUserSummaryResponse] = []


class AdminMonthlyGrantRequest(BaseModel):
    amount: int = Field(
        default=settings.CREDITS_DEFAULT_MONTHLY_GRANT,
        gt=0,
        le=settings.ADMIN_CREDIT_GRANT_MAX,
    )
    period_key: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    memo_prefix: str = Field(
        default="Monthly research grant", min_length=3, max_length=120
    )


class AdminMonthlyGrantResponse(BaseModel):
    period_key: str
    amount: int
    granted_user_count: int
    skipped_user_count: int
    granted_user_ids: list[str] = []


class AccessRequestSummary(BaseModel):
    id: str
    email: str
    display_name: str
    status: str
    invite_used: bool
    promo_code_used: Optional[str] = None
    notes: Optional[str] = None
    created_at: str


class AdminAccessRequestsResponse(BaseModel):
    total: int
    requests: list[AccessRequestSummary] = []


class AdminApproveAccessRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


class AdminRejectAccessRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


# ---- Endpoints ----


@router.post("/estimate", response_model=CreditEstimateResponse)
async def estimate_credits(
    request: CreditEstimateRequest,
    user: UserProfile = Depends(require_auth),
):
    """Estimate token-to-credit charge using configured multipliers."""
    del user

    input_component = int(
        round(request.prompt_tokens * settings.CREDITS_INPUT_TOKEN_MULTIPLIER)
    )
    output_component = int(
        round(request.completion_tokens * settings.CREDITS_OUTPUT_TOKEN_MULTIPLIER)
    )
    ocr_surcharge = settings.CREDITS_OCR_SURCHARGE if request.uses_ocr else 0
    web_search_surcharge = (
        settings.CREDITS_WEB_SEARCH_SURCHARGE if request.uses_web_search else 0
    )

    estimated_credits = (
        input_component + output_component + ocr_surcharge + web_search_surcharge
    )

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

    meter = CreditMeter(db)
    await meter.ensure_account(user.id)

    repo = CreditAccountRepository(db)
    reconcile = getattr(repo, "reconcile_account_projection", None)
    account = (
        await reconcile(user.id)
        if callable(reconcile)
        else await repo.get_account(user.id)
    )
    if account is not None and callable(reconcile):
        await db.commit()
    if not account:
        return BalanceResponse(
            credits_enabled=True,
            daily_limit=settings.CREDITS_DAILY_LIMIT,
            monthly_limit=settings.CREDITS_MONTHLY_LIMIT,
            soft_limit_pct=settings.CREDITS_SOFT_LIMIT_PCT,
            default_monthly_grant=settings.CREDITS_DEFAULT_MONTHLY_GRANT,
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
        default_monthly_grant=settings.CREDITS_DEFAULT_MONTHLY_GRANT,
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


@router.get("/admin/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(
    search: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Return a searchable user list for admin credit operations."""
    del user

    query = (
        select(UserProfile, CreditAccount)
        .outerjoin(CreditAccount, CreditAccount.user_id == UserProfile.id)
        .order_by(UserProfile.created_at.desc())
        .limit(limit)
    )
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                UserProfile.email.ilike(term),
                UserProfile.display_name.ilike(term),
                UserProfile.external_id.ilike(term),
            )
        )

    rows = (await db.execute(query)).all()
    repo = CreditAccountRepository(db)
    corrected_accounts: dict[str, CreditAccount | None] = {}
    reconcile = getattr(repo, "reconcile_account_projection", None)
    if callable(reconcile):
        for profile, _account in rows:
            corrected_accounts[str(profile.id)] = await reconcile(profile.id)
    if corrected_accounts and callable(reconcile):
        await db.commit()
    page_allowance = PageAllowanceService(db)
    return AdminOverviewResponse(
        configured_admin_external_id=get_configured_admin_external_id(),
        credits_enabled=settings.CREDITS_ENABLED,
        default_monthly_grant=settings.CREDITS_DEFAULT_MONTHLY_GRANT,
        default_page_allowance=settings.INGESTION_DEFAULT_PAGE_ALLOWANCE,
        current_grant_period=CreditMeter.current_grant_period_key(),
        users=[
            AdminUserSummaryResponse(
                id=str(profile.id),
                email=profile.email,
                display_name=profile.display_name,
                external_id=profile.external_id,
                created_at=profile.created_at.isoformat() if profile.created_at else "",
                balance=(corrected_accounts.get(str(profile.id)) or account).balance if (corrected_accounts.get(str(profile.id)) or account) else 0,
                lifetime_granted=(corrected_accounts.get(str(profile.id)) or account).lifetime_granted if (corrected_accounts.get(str(profile.id)) or account) else 0,
                lifetime_used=(corrected_accounts.get(str(profile.id)) or account).lifetime_used if (corrected_accounts.get(str(profile.id)) or account) else 0,
                is_admin=is_admin_user(profile),
                parse_page_limit=int(profile.parse_page_limit or 0),
                parse_page_used=int(profile.parse_page_used or 0),
                parse_page_reserved=int(profile.parse_page_reserved or 0),
                parse_page_remaining=page_allowance.remaining_pages_for(profile),
            )
            for profile, account in rows
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
        metadata={
            "granted_by_external_id": user.external_id,
            "granted_by_user_id": str(user.id),
            "target_user_id": request.user_id,
        },
    )
    await db.commit()

    account = await repo.get_account(target_user_id)
    logger.warning(
        "Admin credit grant issued by %s to user %s for %s credits",
        user.external_id,
        request.user_id,
        request.amount,
    )

    return AdminGrantResponse(
        grant_id=str(grant.id),
        user_id=request.user_id,
        amount=request.amount,
        new_balance=account.balance if account else 0,
    )


@router.post(
    "/admin/page-allowance/grant", response_model=AdminPageAllowanceGrantResponse
)
async def admin_grant_page_allowance(
    request: AdminPageAllowanceGrantRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    import uuid as _uuid

    target_user_id = _uuid.UUID(request.user_id)
    allowance_service = PageAllowanceService(db)
    updated_user = await allowance_service.grant_pages(target_user_id, request.amount)
    await db.commit()
    logger.warning(
        "Admin page allowance grant issued by %s to user %s for %s pages (%s)",
        user.external_id,
        request.user_id,
        request.amount,
        request.memo,
    )
    return AdminPageAllowanceGrantResponse(
        user_id=request.user_id,
        amount=request.amount,
        new_limit=int(updated_user.parse_page_limit or 0),
        remaining_pages=allowance_service.remaining_pages_for(updated_user),
    )


@router.post("/admin/monthly-grant", response_model=AdminMonthlyGrantResponse)
async def admin_issue_monthly_grant(
    request: AdminMonthlyGrantRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Issue the operator-managed monthly grant once per period for each user."""
    repo = CreditAccountRepository(db)
    period_key = request.period_key or CreditMeter.current_grant_period_key()
    memo = f"{request.memo_prefix} ({period_key})"

    user_rows = await db.execute(
        select(UserProfile.id).order_by(UserProfile.created_at.asc())
    )
    user_ids = list(user_rows.scalars().all())

    granted_user_ids: list[str] = []
    skipped_user_count = 0
    for target_user_id in user_ids:
        if await repo.has_grant(target_user_id, source="monthly_grant", memo=memo):
            skipped_user_count += 1
            continue

        await repo.issue_grant(
            target_user_id,
            amount=request.amount,
            source="monthly_grant",
            memo=memo,
            metadata={
                "grant_period": period_key,
                "granted_by_external_id": user.external_id,
                "granted_by_user_id": str(user.id),
            },
        )
        granted_user_ids.append(str(target_user_id))

    await db.commit()
    logger.warning(
        "Admin monthly grant refresh issued by %s for period %s: granted=%s skipped=%s",
        user.external_id,
        period_key,
        len(granted_user_ids),
        skipped_user_count,
    )
    return AdminMonthlyGrantResponse(
        period_key=period_key,
        amount=request.amount,
        granted_user_count=len(granted_user_ids),
        skipped_user_count=skipped_user_count,
        granted_user_ids=granted_user_ids,
    )


# ---------------------------------------------------------------------------
# Alpha access request admin endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/access-requests", response_model=AdminAccessRequestsResponse)
async def admin_list_access_requests(
    status_filter: Optional[str] = Query(
        default=None, alias="status", pattern=r"^(pending|approved|rejected)$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """List alpha access requests (filterable by status)."""
    del user
    query = (
        select(AlphaAccessRequest)
        .order_by(AlphaAccessRequest.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(AlphaAccessRequest.status == status_filter)
    rows = (await db.execute(query)).scalars().all()
    return AdminAccessRequestsResponse(
        total=len(rows),
        requests=[
            AccessRequestSummary(
                id=str(r.id),
                email=r.email,
                display_name=r.display_name,
                status=r.status,
                invite_used=r.invite_used,
                promo_code_used=r.promo_code_used,
                notes=r.notes,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows
        ],
    )


@router.post(
    "/admin/access-requests/{request_id}/approve", response_model=AccessRequestSummary
)
async def admin_approve_access_request(
    request_id: str,
    body: AdminApproveAccessRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Approve an alpha access request and send the invite email."""
    import uuid as _uuid

    result = await db.execute(
        select(AlphaAccessRequest).where(
            AlphaAccessRequest.id == _uuid.UUID(request_id)
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found"
        )
    if req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already {req.status}",
        )

    req.status = "approved"
    req.invite_token = AlphaAccessRequest.generate_token()
    if body.notes:
        req.notes = body.notes
    await db.commit()
    await db.refresh(req)

    email_subject, email_html = build_alpha_invite_email(
        req.display_name, req.invite_token
    )
    await send_email(req.email, email_subject, email_html)

    logger.warning(
        "Admin %s approved alpha access for %s (request %s)",
        user.external_id,
        req.email,
        request_id,
    )
    return AccessRequestSummary(
        id=str(req.id),
        email=req.email,
        display_name=req.display_name,
        status=req.status,
        invite_used=req.invite_used,
        promo_code_used=req.promo_code_used,
        notes=req.notes,
        created_at=req.created_at.isoformat() if req.created_at else "",
    )


@router.post(
    "/admin/access-requests/{request_id}/reject", response_model=AccessRequestSummary
)
async def admin_reject_access_request(
    request_id: str,
    body: AdminRejectAccessRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Reject an alpha access request."""
    import uuid as _uuid

    result = await db.execute(
        select(AlphaAccessRequest).where(
            AlphaAccessRequest.id == _uuid.UUID(request_id)
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found"
        )
    if req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request is already {req.status}",
        )

    req.status = "rejected"
    if body.notes:
        req.notes = body.notes
    await db.commit()
    await db.refresh(req)

    logger.warning(
        "Admin %s rejected alpha access for %s (request %s)",
        user.external_id,
        req.email,
        request_id,
    )
    return AccessRequestSummary(
        id=str(req.id),
        email=req.email,
        display_name=req.display_name,
        status=req.status,
        invite_used=req.invite_used,
        promo_code_used=req.promo_code_used,
        notes=req.notes,
        created_at=req.created_at.isoformat() if req.created_at else "",
    )
