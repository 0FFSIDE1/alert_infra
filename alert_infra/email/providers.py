"""Legacy template-email provider adapters.

The active alert dispatcher uses ``ResendEmailTransport``,
``SendGridEmailTransport``, and ``SMTPEmailTransport`` from
``alert_infra.email.transports``. These adapters remain only for older callers
of ``alert_infra.email.services.EmailService`` and the legacy
``send_notify_email_task`` task.
"""

from .interfaces import EmailProvider
from .helper import send_with_resend, send_with_sendgrid, send_with_smtp

class ResendProvider(EmailProvider):
    name = "resend"

    def send(self, to, subject, html, text):
        send_with_resend(to, subject, html, text)

class SendGridProvider(EmailProvider):
    name = "sendgrid"

    def send(self, to, subject, html, text):
        send_with_sendgrid(to, subject, html, text)

class SMTPProvider(EmailProvider):
    name = "smtp"

    def send(self, to, subject, html, text):
        send_with_smtp(to, subject, html)
        