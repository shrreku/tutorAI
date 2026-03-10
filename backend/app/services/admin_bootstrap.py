import logging

import bcrypt

from app.api.deps import get_configured_admin_external_id
from app.config import settings
from app.db.database import async_session_factory
from app.db.repositories.session_repo import UserProfileRepository
from app.models.session import UserProfile

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def ensure_bootstrap_admin() -> None:
    """Create or update the single configured admin account for hosted auth.

    This is opt-in and only runs when both ADMIN_BOOTSTRAP_EMAIL and
    ADMIN_BOOTSTRAP_PASSWORD are configured.
    """
    if not settings.AUTH_ENABLED:
        return

    bootstrap_email = (settings.ADMIN_BOOTSTRAP_EMAIL or "").strip().lower()
    bootstrap_password = settings.ADMIN_BOOTSTRAP_PASSWORD or ""
    if not bootstrap_email and not bootstrap_password:
        return
    if not bootstrap_email or not bootstrap_password:
        raise RuntimeError(
            "ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD must either both be set or both be empty."
        )

    configured_admin = get_configured_admin_external_id()
    if configured_admin and configured_admin.lower() != bootstrap_email:
        raise RuntimeError(
            "ADMIN_BOOTSTRAP_EMAIL must match ADMIN_EXTERNAL_ID so the bootstrapped account is the sole admin."
        )

    async with async_session_factory() as db:
        repo = UserProfileRepository(db)
        user = await repo.get_by_email(bootstrap_email)
        if user is None:
            user = await repo.get_by_external_id(bootstrap_email)

        password_hash = _hash_password(bootstrap_password)
        display_name = (settings.ADMIN_BOOTSTRAP_DISPLAY_NAME or "StudyAgent Admin").strip() or "StudyAgent Admin"

        if user is None:
            db.add(
                UserProfile(
                    external_id=bootstrap_email,
                    email=bootstrap_email,
                    display_name=display_name,
                    password_hash=password_hash,
                    preferences={"admin_bootstrapped": True},
                )
            )
            await db.commit()
            logger.warning("Bootstrapped admin account for %s", bootstrap_email)
            return

        user.external_id = bootstrap_email
        user.email = bootstrap_email
        user.display_name = display_name
        user.password_hash = password_hash
        preferences = dict(user.preferences or {})
        preferences["admin_bootstrapped"] = True
        user.preferences = preferences
        db.add(user)
        await db.commit()
        logger.warning("Synchronized bootstrapped admin credentials for %s", bootstrap_email)