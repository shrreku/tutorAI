import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.services.ingestion.page_allowance import PageAllowanceService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Result:
    def __init__(self, rowcount=1, user=None):
        self.rowcount = rowcount
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _Db:
    def __init__(self, user):
        self.user = user
        self.execute_calls = []
        self.added = []
        self.flushed = 0
        self.refreshed = 0

    async def execute(self, stmt):
        self.execute_calls.append(str(stmt))
        text = str(stmt)
        if "FROM user_profile" in text:
            return _ScalarResult(self.user)
        return _Result(rowcount=1, user=self.user)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def refresh(self, _obj):
        self.refreshed += 1


def test_page_allowance_ensure_user_defaults_backfills_missing_fields():
    user = SimpleNamespace(
        id=uuid4(),
        parse_page_limit=None,
        parse_page_used=None,
        parse_page_reserved=None,
    )
    db = _Db(user)
    service = PageAllowanceService(db)

    updated = asyncio.run(service.ensure_user_defaults(user))

    assert updated.parse_page_limit == 800
    assert updated.parse_page_used == 0
    assert updated.parse_page_reserved == 0
    assert db.flushed == 1
    assert db.refreshed == 1


def test_page_allowance_finalize_charges_max_of_actual_and_reserved():
    user = SimpleNamespace(
        id=uuid4(),
        parse_page_limit=800,
        parse_page_used=120,
        parse_page_reserved=6,
    )
    db = _Db(user)
    service = PageAllowanceService(db)

    charged = asyncio.run(service.finalize_pages(user.id, actual_pages=9, reserved_pages=6))

    assert charged == 9
    assert db.flushed >= 1
    assert any("parse_page_used" in call for call in db.execute_calls)


def test_page_allowance_release_caps_to_reserved_balance():
    user = SimpleNamespace(
        id=uuid4(),
        parse_page_limit=800,
        parse_page_used=120,
        parse_page_reserved=4,
    )
    db = _Db(user)
    service = PageAllowanceService(db)

    asyncio.run(service.release_pages(user.id, reserved_pages=10))

    assert db.flushed >= 1
    assert any("parse_page_reserved" in call for call in db.execute_calls)


def test_page_allowance_remaining_pages_never_negative():
    user = SimpleNamespace(parse_page_limit=10, parse_page_used=9, parse_page_reserved=5)

    remaining = PageAllowanceService.remaining_pages_for(user)

    assert remaining == 0
