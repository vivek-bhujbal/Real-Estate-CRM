import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_password_reset_email(*, recipient: str, full_name: str, token: str) -> bool:
    settings = get_settings()
    if (
        settings.password_reset_delivery != "smtp"
        or not settings.smtp_host
        or settings.smtp_from_email is None
    ):
        logger.warning("Password reset delivery is disabled; no reset message was sent")
        return False

    # The token is placed in the URL fragment so browsers do not send it to the
    # frontend server, reverse proxy access logs, or Referer headers.
    reset_url = f"{settings.public_web_url.rstrip('/')}/reset-password#token={quote(token)}"
    message = EmailMessage()
    message["Subject"] = "Reset your EstateOps password"
    message["From"] = str(settings.smtp_from_email)
    message["To"] = recipient
    message.set_content(
        f"Hello {full_name},\n\n"
        "A password reset was requested for your EstateOps account. "
        f"Open this link to choose a new password:\n\n{reset_url}\n\n"
        f"This link expires in {settings.password_reset_ttl_minutes} minutes and can be used once. "
        "If you did not request this, you can ignore this message."
    )

    try:
        await asyncio.to_thread(_send_smtp, message)
    except Exception:
        logger.exception("Password reset email delivery failed")
        return False
    return True


def _send_smtp(message: EmailMessage) -> None:
    settings = get_settings()
    if settings.smtp_host is None:
        raise RuntimeError("SMTP is not configured")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
            smtp.login(settings.smtp_username, password)
        smtp.send_message(message)
