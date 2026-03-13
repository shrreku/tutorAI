"""Tests for alpha access gate — request-access endpoint and gated register.

Unit tests only (no real database): we monkeypatch repositories and SQLAlchemy
sessions so these run entirely in-process and are fast.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import auth as auth_module
from app.api.v1 import billing as billing_module
from app.config import settings
from app.models.alpha import AlphaAccessRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyDb:
    """Minimal async session stub."""

    def __init__(self, execute_return=None):
        self._added = []
        self._execute_return = execute_return
        self.committed = False

    async def execute(self, *_a, **_kw):
        return self._execute_return

    def add(self, obj):
        self._added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        pass  # no-op


class _ScalarResult:
    """Minimal row-result stub for .scalar_one_or_none()."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


# ---------------------------------------------------------------------------
# request-access endpoint tests
# ---------------------------------------------------------------------------


def test_request_access_queues_pending_when_alpha_disabled(monkeypatch):
    """When ALPHA_ACCESS_ENABLED is False the endpoint still queues a request."""
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", False, raising=False)
    # No existing record
    db = _DummyDb(execute_return=_ScalarResult(None))

    resp = asyncio.run(
        auth_module.request_access(
            body=auth_module.RequestAccessRequest(
                email="new@example.com",
                display_name="New User",
            ),
            db=db,
            _=None,
        )
    )

    assert resp.status in ("submitted",)
    assert len(db._added) == 1
    assert db._added[0].email == "new@example.com"
    assert db._added[0].status == "pending"
    assert db.committed


def test_request_access_auto_approves_valid_promo(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "TESTCODE,OTHER", raising=False)
    db = _DummyDb(execute_return=_ScalarResult(None))

    resp = asyncio.run(
        auth_module.request_access(
            body=auth_module.RequestAccessRequest(
                email="promo@example.com",
                display_name="Promo User",
                promo_code="TESTCODE",
            ),
            db=db,
            _=None,
        )
    )

    assert resp.status == "approved"
    assert db._added[0].status == "approved"
    assert db._added[0].promo_code_used == "TESTCODE"


def test_request_access_treats_invalid_promo_as_pending(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "REALCODE", raising=False)
    db = _DummyDb(execute_return=_ScalarResult(None))

    resp = asyncio.run(
        auth_module.request_access(
            body=auth_module.RequestAccessRequest(
                email="bad@example.com",
                display_name="Bad User",
                promo_code="WRONGCODE",
            ),
            db=db,
            _=None,
        )
    )

    assert resp.status == "submitted"
    assert db._added[0].status == "pending"


def test_request_access_is_idempotent_for_existing_email(monkeypatch):
    """If the email already exists we must NOT add a second row."""
    existing = AlphaAccessRequest(
        email="dup@example.com", display_name="Dup", status="pending"
    )
    db = _DummyDb(execute_return=_ScalarResult(existing))

    resp = asyncio.run(
        auth_module.request_access(
            body=auth_module.RequestAccessRequest(
                email="dup@example.com",
                display_name="Dup",
            ),
            db=db,
            _=None,
        )
    )

    assert resp.status == "submitted"
    assert len(db._added) == 0  # no new row


# ---------------------------------------------------------------------------
# register — alpha gate ON
# ---------------------------------------------------------------------------


def _make_register_patches(monkeypatch, *, existing_user=None, alpha_request=None):
    """Set up monkeypatches for the register endpoint."""

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return existing_user

        async def create(self, user):
            user.id = uuid4()
            return user

    class _Meter:
        def __init__(self, _db):
            pass

        async def issue_signup_grant_if_missing(self, _user_id):
            pass

    class _SelectResult:
        def scalar_one_or_none(self):
            return alpha_request

    monkeypatch.setattr(auth_module, "UserProfileRepository", _Repo)
    monkeypatch.setattr(auth_module, "CreditMeter", _Meter)
    return _SelectResult()


def test_register_blocked_without_invite_when_alpha_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "", raising=False)
    _make_register_patches(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_module.register(
                body=auth_module.RegisterRequest(
                    email="blocked@example.com",
                    password="Password123!",
                    display_name="Blocked",
                ),
                db=_DummyDb(),
                _=None,
            )
        )
    assert exc.value.status_code == 403


def test_register_blocked_with_invalid_invite_token(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "", raising=False)
    # No matching request found for this token
    _make_register_patches(monkeypatch, alpha_request=None)
    db = _DummyDb(execute_return=_ScalarResult(None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_module.register(
                body=auth_module.RegisterRequest(
                    email="hacker@example.com",
                    password="Password123!",
                    display_name="Hacker",
                    invite_token="some-bad-token",
                ),
                db=db,
                _=None,
            )
        )
    assert exc.value.status_code == 403


def test_register_blocked_when_invite_email_mismatch(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "", raising=False)
    _make_register_patches(monkeypatch)

    alpha_req = AlphaAccessRequest(
        email="approved@example.com",
        display_name="A",
        status="approved",
        invite_token="good-token",
    )
    alpha_req.invite_used = False
    db = _DummyDb(execute_return=_ScalarResult(alpha_req))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_module.register(
                body=auth_module.RegisterRequest(
                    email="different@example.com",  # doesn't match invite
                    password="Password123!",
                    display_name="A",
                    invite_token="good-token",
                ),
                db=db,
                _=None,
            )
        )
    assert exc.value.status_code == 403


def test_register_succeeds_with_valid_invite_token(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_ID", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_IDS", "", raising=False)

    alpha_req = AlphaAccessRequest(
        email="invited@example.com",
        display_name="Invited",
        status="approved",
        invite_token="valid-token-xyz",
    )
    alpha_req.invite_used = False

    _make_register_patches(monkeypatch)
    db = _DummyDb(execute_return=_ScalarResult(alpha_req))

    response = asyncio.run(
        auth_module.register(
            body=auth_module.RegisterRequest(
                email="invited@example.com",
                password="Password123!",
                display_name="Invited",
                invite_token="valid-token-xyz",
            ),
            db=db,
            _=None,
        )
    )

    assert response.user.email == "invited@example.com"
    assert alpha_req.invite_used is True  # marked consumed


def test_register_succeeds_with_valid_promo_code_when_alpha_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "LAUNCH2026", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_ID", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_IDS", "", raising=False)

    _make_register_patches(monkeypatch)

    response = asyncio.run(
        auth_module.register(
            body=auth_module.RegisterRequest(
                email="promo@example.com",
                password="Password123!",
                display_name="Promo User",
                promo_code="LAUNCH2026",
            ),
            db=_DummyDb(),
            _=None,
        )
    )

    assert response.user.email == "promo@example.com"


def test_register_blocked_with_wrong_promo_when_alpha_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALPHA_PROMO_CODES", "REALCODE", raising=False)
    _make_register_patches(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_module.register(
                body=auth_module.RegisterRequest(
                    email="wrong@example.com",
                    password="Password123!",
                    display_name="Wrong",
                    promo_code="BADCODE",
                ),
                db=_DummyDb(),
                _=None,
            )
        )
    assert exc.value.status_code == 403


def test_register_open_when_alpha_disabled(monkeypatch):
    """Without ALPHA_ACCESS_ENABLED, no token needed."""
    monkeypatch.setattr(settings, "ALPHA_ACCESS_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_ID", "", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_IDS", "", raising=False)
    _make_register_patches(monkeypatch)

    response = asyncio.run(
        auth_module.register(
            body=auth_module.RegisterRequest(
                email="open@example.com",
                password="Password123!",
                display_name="Open",
            ),
            db=_DummyDb(),
            _=None,
        )
    )

    assert response.user.email == "open@example.com"


# ---------------------------------------------------------------------------
# AlphaAccessRequest model helpers
# ---------------------------------------------------------------------------


def test_invite_token_generation_is_unique():
    tokens = {AlphaAccessRequest.generate_token() for _ in range(20)}
    assert len(tokens) == 20  # all unique


def test_invite_token_is_url_safe():
    import re

    token = AlphaAccessRequest.generate_token()
    assert re.match(r"^[A-Za-z0-9_\-]+$", token)
    assert len(token) >= 40


# ---------------------------------------------------------------------------
# Billing admin approve/reject endpoint tests
# ---------------------------------------------------------------------------


def test_admin_approve_sets_token_and_calls_email(monkeypatch):
    req_id = str(uuid4())
    alpha_req = AlphaAccessRequest(
        email="pending@example.com",
        display_name="Pending",
        status="pending",
    )
    alpha_req.id = uuid4()
    alpha_req.invite_token = None
    alpha_req.invite_used = False
    alpha_req.promo_code_used = None
    alpha_req.notes = None
    from datetime import datetime, timezone

    alpha_req.created_at = datetime.now(timezone.utc)

    emails_sent = []

    async def _fake_send_email(to, subject, html, text=None):
        emails_sent.append((to, subject))
        return True

    monkeypatch.setattr(billing_module, "send_email", _fake_send_email)

    db = _DummyDb(execute_return=_ScalarResult(alpha_req))
    admin_user = SimpleNamespace(id=uuid4(), external_id="admin@example.com")

    asyncio.run(
        billing_module.admin_approve_access_request(
            request_id=req_id,
            body=billing_module.AdminApproveAccessRequest(notes="Looks good"),
            db=db,
            user=admin_user,
        )
    )

    assert alpha_req.status == "approved"
    assert alpha_req.invite_token is not None
    assert alpha_req.notes == "Looks good"
    assert db.committed
    assert len(emails_sent) == 1
    assert emails_sent[0][0] == "pending@example.com"


def test_admin_approve_rejects_already_approved(monkeypatch):
    alpha_req = AlphaAccessRequest(
        email="done@example.com", display_name="Done", status="approved"
    )
    alpha_req.id = uuid4()
    from datetime import datetime, timezone

    alpha_req.created_at = datetime.now(timezone.utc)

    monkeypatch.setattr(billing_module, "send_email", lambda *a, **kw: None)
    db = _DummyDb(execute_return=_ScalarResult(alpha_req))
    admin_user = SimpleNamespace(id=uuid4(), external_id="admin@example.com")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            billing_module.admin_approve_access_request(
                request_id=str(uuid4()),
                body=billing_module.AdminApproveAccessRequest(),
                db=db,
                user=admin_user,
            )
        )
    assert exc.value.status_code == 409


def test_admin_reject_sets_status(monkeypatch):
    req_id = str(uuid4())
    alpha_req = AlphaAccessRequest(
        email="nope@example.com", display_name="Nope", status="pending"
    )
    alpha_req.id = uuid4()
    alpha_req.invite_token = None
    alpha_req.invite_used = False
    alpha_req.promo_code_used = None
    alpha_req.notes = None
    from datetime import datetime, timezone

    alpha_req.created_at = datetime.now(timezone.utc)

    db = _DummyDb(execute_return=_ScalarResult(alpha_req))
    admin_user = SimpleNamespace(id=uuid4(), external_id="admin@example.com")

    asyncio.run(
        billing_module.admin_reject_access_request(
            request_id=req_id,
            body=billing_module.AdminRejectAccessRequest(notes="Not eligible"),
            db=db,
            user=admin_user,
        )
    )

    assert alpha_req.status == "rejected"
    assert alpha_req.notes == "Not eligible"
    assert db.committed


def test_admin_approve_returns_404_for_missing_request(monkeypatch):
    monkeypatch.setattr(billing_module, "send_email", lambda *a, **kw: None)
    db = _DummyDb(execute_return=_ScalarResult(None))
    admin_user = SimpleNamespace(id=uuid4(), external_id="admin@example.com")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            billing_module.admin_approve_access_request(
                request_id=str(uuid4()),
                body=billing_module.AdminApproveAccessRequest(),
                db=db,
                user=admin_user,
            )
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Email service tests
# ---------------------------------------------------------------------------


def test_build_alpha_invite_email_contains_token(monkeypatch):
    monkeypatch.setattr(
        settings, "APP_BASE_URL", "https://app.example.com", raising=False
    )
    monkeypatch.setattr(
        settings, "RESEND_FROM_EMAIL", "test@example.com", raising=False
    )

    from app.services.email import build_alpha_invite_email

    subject, html = build_alpha_invite_email("Alice", "tok-abc")

    assert "Alice" in html
    assert "tok-abc" in html
    assert "https://app.example.com/register?invite=tok-abc" in html
    assert "invite" in subject.lower() or "alpha" in subject.lower()


def test_send_email_skips_when_no_api_key(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_API_KEY", "", raising=False)

    from app.services.email import send_email

    result = asyncio.run(send_email("x@y.com", "Hi", "<p>Hi</p>"))
    assert result is False


# ---------------------------------------------------------------------------
# Signup grant amount
# ---------------------------------------------------------------------------


def test_signup_grant_uses_credits_signup_grant_setting(monkeypatch):
    """Verify meter issues CREDITS_SIGNUP_GRANT credits, not CREDITS_DEFAULT_MONTHLY_GRANT."""
    from app.services.credits.meter import CreditMeter

    monkeypatch.setattr(settings, "CREDITS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "CREDITS_SIGNUP_GRANT", 500, raising=False)

    issued = []

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_account(self, _uid):
            return None

        async def has_grant(self, _uid, source, memo):
            return False

        async def issue_grant(self, uid, *, amount, source, memo, metadata):
            issued.append(amount)
            return SimpleNamespace(id=uuid4())

    # Need a stub for MeteringRepository too
    class _MeteringRepo:
        def __init__(self, _db):
            pass

    monkeypatch.setattr("app.services.credits.meter.CreditAccountRepository", _Repo)
    monkeypatch.setattr("app.services.credits.meter.MeteringRepository", _MeteringRepo)

    class _FakeDb:
        pass

    meter = CreditMeter(_FakeDb())
    granted = asyncio.run(meter.issue_signup_grant_if_missing(uuid4()))

    assert granted is True
    assert issued == [500]
