"""Compatibility helpers for legacy template-email integrations.

The active alert dispatcher uses transports from ``alert_infra.email.transports``.
This provider chain remains for callers of the older
``send_notify_email_task`` workflow.
"""

from __future__ import annotations

from .providers import ResendProvider, SMTPProvider, SendGridProvider


class EmailService:
    """Try configured legacy email providers in order."""

    def __init__(self, providers=None):
        self.providers = providers or [ResendProvider(), SendGridProvider(), SMTPProvider()]

    def send(self, to, subject, html, text):
        last_error = None
        for provider in self.providers:
            try:
                provider.send(to, subject, html, text)
                return provider.name
            except Exception as exc:  # noqa: BLE001 - compatibility fallback chain.
                last_error = exc
        if last_error:
            raise last_error
        raise RuntimeError("no email providers configured")


def get_email_service() -> EmailService:
    return EmailService()
