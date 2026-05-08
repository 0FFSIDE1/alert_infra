from django.core.cache import cache
from email.mime.text import MIMEText
import requests
from django.conf import settings
import logging
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
import smtplib


logger = logging.getLogger('django')

def provider_down(name):
    return cache.get(f"{name}_down")

def mark_down(name):
    cache.set(f"{name}_down", True, timeout=300)  # 5 minutes

def send_email(to_email, subject, template_path, context):
    try:
        from core.tasks.utils import send_notify_email_task

        is_otp = context.get('is_otp', False)
        data = {"context": context, "is_otp": is_otp}
        send_notify_email_task.delay(to_email, subject, template_path, data)
        logger.info(f"Email queued for: {to_email} for {subject}")
    except Exception as exc:
        logger.error(f"❌ Failed to queue email to {to_email}: {str(exc)}")


def send_with_resend(to_emails, subject, html, text):
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": to_emails,
            "subject": subject,
            "html": html,
            "text": text,
        },
        timeout=8,
    )

    if response.status_code not in (200, 201):
        raise Exception(f"Resend failed: {response.text}")


def send_with_sendgrid(to_emails, subject, html, text):
    sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)

    message = Mail(
        from_email=Email(settings.DEFAULT_FROM_EMAIL),
        to_emails=[To(e) for e in to_emails],
        subject=subject,
        plain_text_content=text,
        html_content=html,
    )

    response = sg.send(message)

    if response.status_code not in (200, 201, 202):
        raise Exception(f"SendGrid failed: {response.status_code}")
    
def send_with_smtp(to_emails, subject, html):
    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = settings.DEFAULT_FROM_EMAIL
    msg["To"] = ", ".join(to_emails)

    server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=8)
    server.starttls()
    server.login(settings.SMTP_HOST_USER, settings.SMTP_HOST_PASSWORD)
    server.sendmail(settings.DEFAULT_FROM_EMAIL, to_emails, msg.as_string())
    server.quit()
