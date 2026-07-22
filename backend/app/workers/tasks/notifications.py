"""Notification worker tasks: send email deliveries with bounded retry.

Critical reminders route to the `critical` queue (worker-fast) so heavy media/AI
work cannot delay them. Each attempt is recorded on the delivery row.
"""

from __future__ import annotations

import uuid

from app.core.observability import get_logger
from app.db.session import session_scope
from app.services.mail.base import MailError, MailMessage
from app.services.mail.providers.smtp import SmtpMailGateway
from app.workers.celery_app import celery

log = get_logger("worker.notifications")


@celery.task(name="app.workers.tasks.notifications.send_email", bind=True, max_retries=5)
def send_email(self, notification_id: str) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.models.foundation import User
    from app.models.notifications import Notification, NotificationDelivery

    with session_scope() as s:
        notification = s.get(Notification, uuid.UUID(notification_id))
        if notification is None:
            return
        delivery = s.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id,
                NotificationDelivery.channel == "email",
            )
        )
        if delivery is None or delivery.status == "sent":
            return
        user = s.get(User, notification.user_id)
        if user is None:
            return
        gateway = SmtpMailGateway()
        if not gateway.configured:
            delivery.status = "failed"
            delivery.last_error = "smtp_unconfigured"
            return
        delivery.status = "sending"
        try:
            gateway.send(
                MailMessage(to=user.email, subject=notification.title, text_body=notification.body)
            )
            delivery.status = "sent"
        except MailError as exc:
            delivery.last_error = str(exc)[:500]
            delivery.attempt_no += 1
            delivery.status = "failed" if exc.permanent else "pending"
            if not exc.permanent:
                raise self.retry(countdown=min(2**delivery.attempt_no, 300), exc=exc) from exc


@celery.task(name="app.workers.tasks.notifications.send_critical_reminder")
def send_critical_reminder(notification_id: str) -> None:
    # Critical reminders reuse the same delivery path but on the critical queue.
    send_email.run(notification_id)


@celery.task(name="app.workers.tasks.notifications.scan_due_reminders")
def scan_due_reminders() -> int:
    """Claim due reminders and dispatch them (Beat-triggered every minute)."""
    from app.modules.notifications import reminder_service

    dispatched = 0
    with session_scope() as s:
        due = reminder_service.claim_due_reminders(s)
        for reminder in due:
            reminder_service.dispatch_reminder(s, reminder)
            dispatched += 1
    return dispatched
