"""Legacy Resend, SendGrid, and SMTP provider adapters.

These adapters are used only by ``alert_infra.email.services.EmailService``
and the legacy ``send_notify_email_task`` task. They are intentionally not
wired into ``AlertDispatcher`` or ``alert_infra.django.build_dispatcher``.
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
        