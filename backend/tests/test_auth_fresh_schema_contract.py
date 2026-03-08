import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.config import settings
from app.db.database import async_session_factory
from app.main import app


def test_migrated_schema_supports_register_and_login():
    settings.AUTH_ENFORCE_STRONG_SECRET = False
    email = f"schema-{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"

    async def _assert_password_hash_column():
        async with async_session_factory() as db:
            result = await db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'user_profile'
                    """
                )
            )
            columns = {row[0] for row in result}
            assert "password_hash" in columns

            await db.execute(
                text("DELETE FROM user_profile WHERE email = :email"),
                {"email": email},
            )
            await db.commit()

    import asyncio

    try:
        asyncio.run(_assert_password_hash_column())
    except (SQLAlchemyError, OSError, PermissionError) as exc:
        pytest.skip(f"Database not reachable in current environment: {exc}")

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": "Schema Test",
                "consent_training": False,
            },
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == 200
        assert login_response.json()["access_token"]

    asyncio.run(_assert_password_hash_column())
