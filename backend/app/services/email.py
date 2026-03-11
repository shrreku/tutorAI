"""Minimal email sending service using the Resend API.

Resend (https://resend.com) has a dead-simple REST API and a generous free tier
(3,000 emails/month).  If RESEND_API_KEY is not configured, email is silently
skipped and a warning is logged — useful during local development.
"""
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_SEND_URL = "https://api.resend.com/emails"


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
) -> bool:
    """Send a transactional email via Resend.

    Returns True if the API call succeeded, False otherwise.
    If RESEND_API_KEY is not set, logs a warning and returns False.
    """
    if not settings.RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY not configured — skipping email to %s (subject: %s)",
            to, subject,
        )
        return False

    payload: dict = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_SEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            )
            if resp.status_code not in (200, 201):
                logger.error("Resend API error %s: %s", resp.status_code, resp.text)
                return False
            logger.info("Email sent to %s via Resend (subject: %s)", to, subject)
            return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send email to %s: %s", to, exc)
        return False


def build_alpha_invite_email(display_name: str, invite_token: str) -> tuple[str, str]:
    """Return (subject, html) for an alpha access invite email."""
    register_url = f"{settings.APP_BASE_URL}/register?invite={invite_token}"
    subject = "You're invited to StudyAgent Alpha"
    html = f"""
<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; max-width: 560px; margin: 40px auto; color: #222;">
  <h2 style="color: #4f46e5;">Welcome to StudyAgent Alpha, {display_name}!</h2>
  <p>Your access request has been approved. Click the link below to create your account:</p>
  <p style="margin: 24px 0;">
    <a href="{register_url}"
       style="background:#4f46e5;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;">
      Create My Account
    </a>
  </p>
  <p style="color:#666;font-size:13px;">
    This invite link is personal and can only be used once.
    It expires after your account is created.
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:32px 0;">
  <p style="color:#999;font-size:12px;">
    If you didn't request access to StudyAgent, you can safely ignore this email.
  </p>
</body>
</html>
""".strip()
    return subject, html
