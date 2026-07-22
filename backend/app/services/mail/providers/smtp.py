"""SMTP MailGateway with required TLS and stable error categories.

Prefers implicit TLS (465); STARTTLS (587) must succeed or the send fails. 4xx
responses are transient (retryable); 5xx are permanent. When SMTP is not
configured the gateway reports itself unavailable and callers degrade.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings
from app.services.mail.base import MailError, MailMessage, MailResult


class SmtpMailGateway:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def configured(self) -> bool:
        s = self._settings
        return bool(s.smtp_host and s.resolved_smtp_password)

    def send(self, message: MailMessage) -> MailResult:
        s = self._settings
        if not self.configured:
            raise MailError("SMTP is not configured", permanent=True)

        msg = EmailMessage()
        msg["From"] = s.smtp_from
        msg["To"] = message.to
        msg["Subject"] = message.subject
        msg.set_content(message.text_body)
        if message.html_body:
            msg.add_alternative(message.html_body, subtype="html")

        context = ssl.create_default_context()
        try:
            if s.smtp_tls_mode == "implicit":
                with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=context, timeout=20) as srv:
                    srv.login(s.smtp_user, s.resolved_smtp_password or "")
                    srv.send_message(msg)
            else:
                with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as srv:
                    srv.starttls(context=context)
                    srv.login(s.smtp_user, s.resolved_smtp_password or "")
                    srv.send_message(msg)
        except smtplib.SMTPResponseException as exc:
            permanent = 500 <= exc.smtp_code < 600
            raise MailError(f"SMTP {exc.smtp_code}", permanent=permanent) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise MailError(str(exc), permanent=False) from exc

        return MailResult(provider_message_id=None, accepted=True)
