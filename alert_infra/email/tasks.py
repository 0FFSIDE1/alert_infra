"""Legacy Celery task for template-based notification email.

This task predates the alert transport dispatcher. It can use the legacy
provider chain from ``alert_infra.email.services``, including Resend and
SendGrid, but normal alert delivery does not enqueue or call this task.
"""

from celery import shared_task
from django.template.loader import render_to_string
import logging
from datetime import date
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from typing import List, Dict, Optional
from .services import get_email_service

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_notify_email_task(self, email, subject: str, template_body_path: str, data: Optional[Dict] = None) -> Dict:
    if data is None:
        data = {}

    recipient_list = email if isinstance(email, list) else [email]

    # Validate emails
    try:
        for e in recipient_list:
            validate_email(e)
    except ValidationError:
        logger.error(f"Invalid email: {recipient_list}")
        return {"status": "invalid email"}

    # Context
    support_email = getattr(settings, "SUPPORT_EMAIL", "support@example.com")
    default_context = {
        'supportLink': f'mailto:{support_email}',
        'year': date.today().year,
    }

    user_context = data.get('context', {})
    user_context.update(default_context)
    data['context'] = user_context

    html_content = render_to_string(template_body_path, data["context"])
    plain_text_content = data.get("plain_text", "Please view this email in HTML.")

    service = get_email_service()

    try:
        provider = service.send(
            recipient_list,
            subject,
            html_content,
            plain_text_content
        )
        return {"status": "sent", "provider": provider}

    except Exception as e:
        raise self.retry(
            exc=e,
            countdown=60 * (2 ** self.request.retries),
        )
