# alert_infra

`alert_infra` is a reusable alerting infrastructure package for Python applications. It gives teams one consistent way to build, sanitize, and deliver operational alerts from both plain Python services and Django projects.

The package is intentionally small: the core alert model and dispatcher have no mandatory third-party runtime dependencies, while Django support is isolated under `alert_infra.django`.

## Table of contents

- [What this project provides](#what-this-project-provides)
- [Architecture](#architecture)
- [Installation](#installation)
- [Core concepts](#core-concepts)
- [Non-Django / plain Python usage](#non-django--plain-python-usage)
- [Django usage](#django-usage)
- [Transport configuration](#transport-configuration)
- [Security and redaction](#security-and-redaction)
- [Error handling and delivery results](#error-handling-and-delivery-results)
- [Custom transports](#custom-transports)
- [Testing patterns](#testing-patterns)
- [Compatibility namespace](#compatibility-namespace)
- [API reference](#api-reference)
- [Development](#development)

## What this project provides

Use `alert_infra` when an application needs to notify operations, security, support, or engineering teams about important events such as failed payments, blocked security actions, background-job failures, webhook failures, or critical business-state changes.

Key capabilities:

- Framework-agnostic `Alert` objects with title, message, severity, source, tags, metadata, timestamps, correlation IDs, and request IDs.
- Built-in sensitive metadata redaction before transport delivery.
- Multi-transport dispatching through `AlertDispatcher`.
- Safe partial-failure handling: one broken transport does not prevent other transports from receiving the alert.
- Built-in transports for:
  - No-op/in-memory delivery.
  - SMTP email.
  - Django email backend.
  - Slack incoming webhooks.
  - Telegram Bot API messages.
- Django settings adapter and `send_alert` helper.
- Django request metadata extraction with defensive redaction of sensitive headers.
- Compatibility exports for projects that still import `feature_flag_infra`.

## Architecture

The codebase is split into framework-neutral modules and optional integration modules:

| Module | Purpose |
| --- | --- |
| `alert_infra.alert` | Core `Alert` dataclass and severity validation. |
| `alert_infra.security` | Recursive metadata redaction helpers. |
| `alert_infra.transports` | Transport protocol, delivery result, no-op transport, and dispatcher. |
| `alert_infra.email` | Framework-agnostic SMTP email transport and email formatting helpers. |
| `alert_infra.apps` | Application/webhook transports such as Slack and Telegram. |
| `alert_infra.django` | Django settings loader, Django email transport, request context helper, and `send_alert`. |
| `feature_flag_infra` | Compatibility namespace that re-exports the same public API. |

Typical flow:

1. Your application creates an `Alert` directly, or calls the Django `send_alert` helper.
2. Sensitive metadata is redacted during `Alert` initialization unless explicitly disabled.
3. An `AlertDispatcher` sends the alert to one or more transports.
4. Each transport receives the same sanitized `Alert` object.
5. The dispatcher returns a `DeliveryResult` containing successful and failed transport names.

## Installation

Install the base package for plain Python, SMTP, Slack, and Telegram usage:

```bash
pip install alert-infra
```

Install Django support when using the `alert_infra.django` adapter:

```bash
pip install "alert-infra[django]"
```

For local development from this repository:

```bash
git clone <repository-url>
cd alert_infra
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Core concepts

### Alert

`Alert` is the domain object delivered to all transports.

```python
from alert_infra import Alert

alert = Alert(
    title="Payment provider timeout",
    message="The payment provider did not respond within 10 seconds.",
    severity="critical",
    source="billing-service",
    tags=("payments", "provider"),
    metadata={
        "invoice_id": "INV-1001",
        "provider": "stripe",
        "api_key": "will-be-redacted",
    },
    request_id="req-01HZY...",
)
```

Supported severities are:

- `info`
- `warning`
- `error`
- `critical`

`title` and `message` are required. Invalid severities raise `AlertValidationError`.

Every alert receives a generated `correlation_id` when one is not provided. Naive `created_at` datetimes are treated as UTC.

### Dispatcher

`AlertDispatcher` sends an alert to a list of transports.

```python
from alert_infra import Alert, AlertDispatcher, NoOpTransport

transport = NoOpTransport()
dispatcher = AlertDispatcher([transport])

result = dispatcher.send(Alert(title="Smoke test", message="Alert pipeline is reachable."))

assert result.ok is True
assert result.sent == ("noop",)
```

### DeliveryResult

`dispatcher.send(...)` returns a `DeliveryResult`:

```python
if result.ok:
    print("alert delivered to", result.sent)
else:
    print("successful transports:", result.sent)
    print("failed transports:", result.failed)
```

- `sent` is a tuple of transport names that succeeded.
- `failed` is a dictionary of `{transport_name: exception_class_name}`.
- `ok` is `True` when no transport failed.

## Non-Django / plain Python usage

Plain Python projects should import from the framework-agnostic modules only. Do not import `alert_infra.django` unless Django is installed and configured.

### Minimal no-op example

This is useful for local development or unit tests.

```python
from alert_infra import Alert, AlertDispatcher, NoOpTransport

dispatcher = AlertDispatcher([NoOpTransport()])

result = dispatcher.send(
    Alert(
        title="Local alert",
        message="This alert is stored in memory only.",
        severity="info",
        source="local-script",
    )
)

print(result.sent)  # ("noop",)
```

### SMTP email from environment variables

Set environment variables:

```bash
export ALERT_FROM_EMAIL=alerts@example.com
export ALERT_TO_EMAILS=ops@example.com,security@example.com
export ALERT_SMTP_HOST=smtp.example.com
export ALERT_SMTP_PORT=587
export ALERT_SMTP_USERNAME=alerts@example.com
export ALERT_SMTP_PASSWORD='from-secret-manager'
export ALERT_SMTP_USE_TLS=true
```

Send an email alert:

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.email import SMTPEmailTransport

email_transport = SMTPEmailTransport.from_env()
dispatcher = AlertDispatcher([email_transport])

result = dispatcher.send(
    Alert(
        title="Payment failure",
        message="Payment provider returned HTTP 500.",
        severity="error",
        source="billing-service",
        tags=("payments", "provider"),
        metadata={"invoice_id": "INV-001", "customer_id": 42},
    )
)

if not result.ok:
    # Log or report the failed transport names. Do not log sensitive metadata.
    print(result.failed)
```

### SMTP email with explicit constructor settings

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.email import SMTPEmailTransport

transport = SMTPEmailTransport(
    host="smtp.example.com",
    port=587,
    from_email="alerts@example.com",
    to_emails=["ops@example.com"],
    username="alerts@example.com",
    password="from-secret-manager",
    use_tls=True,
    timeout=8.0,
)

dispatcher = AlertDispatcher([transport])
dispatcher.send(Alert(title="Disk usage high", message="/var is above 90%.", severity="warning"))
```

### Slack webhook alerts

Set an environment variable:

```bash
export ALERT_SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...'
```

Create and use the transport:

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.apps import SlackWebhookTransport

slack = SlackWebhookTransport.from_env()
dispatcher = AlertDispatcher([slack])

dispatcher.send(
    Alert(
        title="Webhook delivery failed",
        message="Customer callback endpoint returned HTTP 503.",
        severity="warning",
        source="webhook-worker",
        metadata={"endpoint_id": "ep_123", "authorization": "Bearer secret"},
    )
)
```

Slack webhook URLs must be absolute `https://` URLs.

### Telegram bot alerts

Set environment variables:

```bash
export ALERT_TELEGRAM_BOT_TOKEN='123456:telegram-token'
export ALERT_TELEGRAM_CHAT_ID='-1001234567890'
```

Create and use the transport:

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.apps import TelegramBotTransport

telegram = TelegramBotTransport.from_env()
dispatcher = AlertDispatcher([telegram])

dispatcher.send(
    Alert(
        title="Nightly import failed",
        message="The supplier CSV import exited with status 1.",
        severity="critical",
        source="import-job",
    )
)
```

### Multiple transports in one dispatcher

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.apps import SlackWebhookTransport, TelegramBotTransport
from alert_infra.email import SMTPEmailTransport

transports = [
    SMTPEmailTransport.from_env(),
    SlackWebhookTransport.from_env(),
    TelegramBotTransport.from_env(),
]

dispatcher = AlertDispatcher(transports)
result = dispatcher.send(Alert(title="API outage", message="Health checks are failing.", severity="critical"))

# Example partial-failure result:
# result.sent == ("email.smtp", "telegram")
# result.failed == {"slack": "AlertDeliveryError"}
```

### Raise when any transport fails

By default the dispatcher returns failures without raising. If your workflow should fail after all transports have been attempted, set `raise_on_failure=True`.

```python
from alert_infra import Alert, AlertDispatcher

result = AlertDispatcher(transports, raise_on_failure=True).send(
    Alert(title="Deployment failed", message="Release job failed after migration step.")
)
```

If any transport fails, `AlertDeliveryError` is raised after the dispatcher attempts every transport.

### Background jobs, CLIs, and scripts

Use one process-wide dispatcher factory so every script uses the same configuration.

```python
# alerts.py
from functools import lru_cache

from alert_infra import AlertDispatcher
from alert_infra.apps import SlackWebhookTransport
from alert_infra.email import SMTPEmailTransport

@lru_cache(maxsize=1)
def get_dispatcher() -> AlertDispatcher:
    return AlertDispatcher([
        SMTPEmailTransport.from_env(),
        SlackWebhookTransport.from_env(),
    ])
```

```python
# nightly_import.py
from alert_infra import Alert
from alerts import get_dispatcher

try:
    run_import()
except Exception as exc:
    get_dispatcher().send(
        Alert(
            title="Nightly import failed",
            message=str(exc.__class__.__name__),
            severity="critical",
            source="nightly-import",
            metadata={"job": "supplier_csv"},
        )
    )
    raise
```

Prefer storing exception class names or safe error summaries in alert metadata. Avoid sending raw exception messages if they may contain credentials or customer data.

## Django usage

Django integration is available from `alert_infra.django` and reads configuration from `settings.ALERT_INFRA`.

### Basic Django settings

```python
# settings.py
ALERT_INFRA = {
    "ENABLED": True,
    "DEFAULT_SEVERITY": "error",
    "REDACT_SENSITIVE_DATA": True,
    "EMAIL": {
        "ENABLED": True,
        "FROM_EMAIL": env("ALERT_FROM_EMAIL"),
        "TO_EMAILS": env.list("ALERT_TO_EMAILS"),
    },
    "SLACK": {
        "ENABLED": True,
        "WEBHOOK_URL": env("ALERT_SLACK_WEBHOOK_URL"),
    },
    "TELEGRAM": {
        "ENABLED": False,
        "BOT_TOKEN": env("ALERT_TELEGRAM_BOT_TOKEN", default=""),
        "CHAT_ID": env("ALERT_TELEGRAM_CHAT_ID", default=""),
    },
}
```

If no transports are enabled, Django builds a dispatcher with `NoOpTransport`. If `ENABLED` is `False`, dispatching is skipped and returns an empty `DeliveryResult`.

### Send an alert from a Django view

```python
from django.http import JsonResponse
from alert_infra.django import send_alert


def update_invoice(request, invoice_id):
    invoice = get_invoice(invoice_id)

    if not invoice.can_transition_to("paid"):
        result = send_alert(
            title="Suspicious invoice update",
            message="Invoice status transition was blocked.",
            severity="warning",
            source="invoice-view",
            tags=("invoice", "security"),
            metadata={
                "invoice_id": invoice.id,
                "user_id": request.user.id,
                "authorization": request.headers.get("Authorization"),
            },
            request=request,
        )
        return JsonResponse({"ok": False, "alert_sent": result.ok}, status=409)

    invoice.mark_paid()
    return JsonResponse({"ok": True})
```

When `request` is provided, the Django helper attaches safe request metadata such as method, path, request ID, user ID, and selected sensitive headers after redaction.

### Send an alert from a Django management command

```python
from django.core.management.base import BaseCommand
from alert_infra.django import send_alert


class Command(BaseCommand):
    help = "Run supplier synchronization"

    def handle(self, *args, **options):
        try:
            synchronize_supplier_data()
        except Exception as exc:
            send_alert(
                title="Supplier sync failed",
                message=exc.__class__.__name__,
                severity="critical",
                source="management-command:supplier_sync",
                metadata={"command": "supplier_sync"},
            )
            raise
```

### Send an alert from a Celery task in a Django project

`alert_infra` does not require Celery, but it can be called from any task once Django settings are loaded.

```python
from celery import shared_task
from alert_infra.django import send_alert


@shared_task(bind=True)
def process_invoice(self, invoice_id):
    try:
        process(invoice_id)
    except Exception as exc:
        send_alert(
            title="Invoice task failed",
            message=exc.__class__.__name__,
            severity="error",
            source="celery:process_invoice",
            metadata={"invoice_id": invoice_id, "task_id": self.request.id},
        )
        raise
```

### Django email backend configuration

When `EMAIL["BACKEND"]` is omitted or set to `"django"`, `alert_infra` uses Django's configured email backend through `EmailMultiAlternatives`.

```python
# settings.py
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = True

ALERT_INFRA = {
    "EMAIL": {
        "ENABLED": True,
        "BACKEND": "django",
        "FROM_EMAIL": "alerts@example.com",
        "TO_EMAILS": ["ops@example.com"],
    }
}
```

### Django with direct SMTP transport

Use the direct SMTP transport instead of Django's email backend by setting `EMAIL["BACKEND"]` to `"smtp"` or by providing `SMTP_HOST`.

```python
ALERT_INFRA = {
    "EMAIL": {
        "ENABLED": True,
        "BACKEND": "smtp",
        "SMTP_HOST": env("ALERT_SMTP_HOST"),
        "SMTP_PORT": env.int("ALERT_SMTP_PORT", default=587),
        "SMTP_USERNAME": env("ALERT_SMTP_USERNAME"),
        "SMTP_PASSWORD": env("ALERT_SMTP_PASSWORD"),
        "SMTP_USE_TLS": True,
        "FROM_EMAIL": env("ALERT_FROM_EMAIL"),
        "TO_EMAILS": env.list("ALERT_TO_EMAILS"),
        "TIMEOUT": 8.0,
    }
}
```

### Django email templates

Django email alerts can use project templates for the subject, text body, and HTML body.

```python
ALERT_INFRA = {
    "EMAIL": {
        "ENABLED": True,
        "FROM_EMAIL": "alerts@example.com",
        "TO_EMAILS": ["ops@example.com"],
        "SUBJECT_TEMPLATE": "alerts/email_subject.txt",
        "BODY_TEMPLATE": "alerts/email_body.txt",
        "HTML_TEMPLATE": "alerts/email_body.html",
        "TEMPLATE_CONTEXT": {"product_name": "Billing Portal"},
    }
}
```

Template context contains:

| Name | Description |
| --- | --- |
| `alert` | The `Alert` object. |
| `alert_dict` | Dictionary returned by `alert.to_dict()`. |
| `metadata` | Redacted alert metadata dictionary. |
| `tags` | List of alert tags. |
| Values from `TEMPLATE_CONTEXT` | Any static values configured in settings. |

Example templates:

```django
{# templates/alerts/email_subject.txt #}
{{ product_name }} {{ alert.severity|upper }}: {{ alert.title }}
```

```django
{# templates/alerts/email_body.txt #}
{{ alert.message }}

Source: {{ alert.source|default:"unknown" }}
Correlation ID: {{ alert.correlation_id }}
{% if metadata.invoice_id %}Invoice: {{ metadata.invoice_id }}{% endif %}
```

```django
{# templates/alerts/email_body.html #}
<h1>{{ alert.title }}</h1>
<p>{{ alert.message }}</p>
<ul>
  <li>Severity: {{ alert.severity }}</li>
  <li>Source: {{ alert.source|default:"unknown" }}</li>
  <li>Correlation ID: {{ alert.correlation_id }}</li>
</ul>
```

The subject renderer collapses line breaks so email subjects remain single-line.

### Django settings reference

`ALERT_INFRA` supports the following keys:

| Key | Default | Description |
| --- | --- | --- |
| `ENABLED` | `True` | Global switch. When `False`, dispatching is skipped. |
| `DEFAULT_SEVERITY` | `"error"` | Severity used by `send_alert` when no severity is provided. |
| `REDACT_SENSITIVE_DATA` | `True` | Whether `Alert` redacts sensitive metadata. |
| `EMAIL` | see below | Email transport settings. |
| `SLACK` | `{"ENABLED": False}` | Slack webhook settings. |
| `TELEGRAM` | `{"ENABLED": False}` | Telegram bot settings. |

Email settings:

| Key | Description |
| --- | --- |
| `ENABLED` | Enable email delivery. |
| `BACKEND` | `"django"` for Django email backend or `"smtp"` for direct SMTP. |
| `FROM_EMAIL` | Sender address. Falls back to `ALERT_FROM_EMAIL`. |
| `TO_EMAILS` | Recipient list or comma-separated string. Falls back to `ALERT_TO_EMAILS`. |
| `TIMEOUT` | Delivery timeout in seconds. |
| `SMTP_HOST` | SMTP hostname for direct SMTP mode. Falls back to `ALERT_SMTP_HOST`. |
| `SMTP_PORT` | SMTP port. Falls back to `ALERT_SMTP_PORT` or `587`. |
| `SMTP_USERNAME` | SMTP username. Falls back to `ALERT_SMTP_USERNAME`. |
| `SMTP_PASSWORD` | SMTP password. Falls back to `ALERT_SMTP_PASSWORD`. |
| `SMTP_USE_TLS` | Whether direct SMTP mode starts TLS. |
| `SUBJECT_TEMPLATE` / `SUBJECT_TEMPLATE_NAME` | Optional Django subject template. |
| `BODY_TEMPLATE` / `BODY_TEMPLATE_NAME` | Optional Django text body template. |
| `HTML_TEMPLATE` / `HTML_TEMPLATE_NAME` | Optional Django HTML body template. |
| `TEMPLATE_CONTEXT` | Static values merged into email template context. |

Slack settings:

| Key | Description |
| --- | --- |
| `ENABLED` | Enable Slack delivery. |
| `WEBHOOK_URL` | Slack incoming webhook URL. Falls back to `ALERT_SLACK_WEBHOOK_URL`. |
| `TIMEOUT` | HTTP timeout in seconds. |

Telegram settings:

| Key | Description |
| --- | --- |
| `ENABLED` | Enable Telegram delivery. |
| `BOT_TOKEN` | Telegram bot token. Falls back to `ALERT_TELEGRAM_BOT_TOKEN`. |
| `CHAT_ID` | Telegram chat ID. Falls back to `ALERT_TELEGRAM_CHAT_ID`. |
| `TIMEOUT` | HTTP timeout in seconds. |

## Transport configuration

### Environment variables

The built-in transports understand these environment variables:

| Variable | Used by | Description |
| --- | --- | --- |
| `ALERT_FROM_EMAIL` | SMTP and Django config | Sender email address. |
| `ALERT_TO_EMAILS` | SMTP and Django config | Comma-separated recipient list. |
| `ALERT_SMTP_HOST` | SMTP | SMTP host. |
| `ALERT_SMTP_PORT` | SMTP | SMTP port. Defaults to `587`. |
| `ALERT_SMTP_USERNAME` | SMTP | SMTP username. |
| `ALERT_SMTP_PASSWORD` | SMTP | SMTP password. |
| `ALERT_SMTP_USE_TLS` | SMTP | `true`, `false`, `1`, `0`, `yes`, or `no`. Defaults to enabled. |
| `ALERT_SLACK_WEBHOOK_URL` | Slack | Slack incoming webhook URL. Must be `https://`. |
| `ALERT_TELEGRAM_BOT_TOKEN` | Telegram | Bot token. |
| `ALERT_TELEGRAM_CHAT_ID` | Telegram | Destination chat ID. |

### Built-in transport names

Transport names appear in `DeliveryResult.sent` and `DeliveryResult.failed`.

| Transport | Name |
| --- | --- |
| `NoOpTransport` | `noop` |
| `SMTPEmailTransport` | `email.smtp` |
| `DjangoEmailTransport` | `email.django` |
| `SlackWebhookTransport` | `slack` |
| `TelegramBotTransport` | `telegram` |

## Security and redaction

`Alert` redacts sensitive metadata by default before any transport receives it.

Sensitive key matching is case-insensitive and treats hyphens as underscores. A key is redacted when it contains one of these terms:

- `password`
- `token`
- `secret`
- `api_key`
- `authorization`
- `cookie`
- `session`
- `csrf`
- `access`
- `refresh`
- `private_key`

Example:

```python
from alert_infra import Alert, REDACTED

alert = Alert(
    title="Authentication anomaly",
    message="Unexpected login attempt.",
    metadata={
        "user_id": 7,
        "authorization": "Bearer secret",
        "nested": {"refresh_token": "secret"},
    },
)

assert alert.metadata["authorization"] == REDACTED
assert alert.metadata["nested"]["refresh_token"] == REDACTED
```

Nested dictionaries, lists, tuples, sets, dataclasses, and many sequence values are traversed. Unsupported values are converted to strings to keep transport payloads serializable.

Only disable redaction when you have a controlled internal transport and have reviewed the data classification risk:

```python
Alert(
    title="Internal debug alert",
    message="Redaction disabled for a controlled test only.",
    metadata={"token": "visible"},
    redact_sensitive_data=False,
)
```

Recommended security practices:

- Load credentials from environment variables, secret managers, or Django settings.
- Do not hardcode webhook URLs, bot tokens, SMTP passwords, or API keys in source control.
- Do not put raw request bodies, raw exception strings, cookies, or authorization headers in metadata.
- Prefer stable identifiers such as invoice IDs, user IDs, request IDs, and job IDs.
- Keep dispatcher logs free of raw alert metadata. The built-in dispatcher logs transport names and exception class names only.

## Error handling and delivery results

The project defines these exceptions:

| Exception | Raised when |
| --- | --- |
| `AlertValidationError` | An alert is invalid, such as missing title/message or unsupported severity. |
| `AlertConfigurationError` | A transport is configured unsafely or incompletely. |
| `AlertDeliveryError` | A transport fails while delivering an alert. |

Dispatcher behavior:

```python
result = dispatcher.send(alert)

if result.failed:
    # Example: {"slack": "AlertDeliveryError"}
    logger.warning("Some alert transports failed: %s", result.failed)
```

The dispatcher attempts all transports even if one fails. Set `raise_on_failure=True` to raise `AlertDeliveryError` after all transports are attempted.

## Custom transports

A transport is any object with:

- a `name` attribute, and
- a `send(alert: Alert) -> None` method.

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.exceptions import AlertDeliveryError


class PagerDutyTransport:
    name = "pagerduty"

    def __init__(self, client, service_id: str) -> None:
        self.client = client
        self.service_id = service_id

    def send(self, alert: Alert) -> None:
        payload = {
            "summary": f"[{alert.severity.upper()}] {alert.title}",
            "source": alert.source or "unknown",
            "severity": alert.severity,
            "custom_details": alert.to_dict(),
        }
        try:
            self.client.trigger_incident(self.service_id, payload)
        except Exception as exc:
            raise AlertDeliveryError("PagerDuty alert delivery failed") from exc


dispatcher = AlertDispatcher([PagerDutyTransport(client, "svc_123")])
dispatcher.send(Alert(title="Queue backlog high", message="More than 10,000 jobs are pending."))
```

For webhook-style custom transports, prefer injecting an HTTP client into the transport. This makes unit tests deterministic and avoids real network calls.

## Testing patterns

### Test alert dispatch without external services

```python
from alert_infra import Alert, AlertDispatcher


class RecordingTransport:
    name = "recording"

    def __init__(self):
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


def test_dispatches_alert():
    transport = RecordingTransport()
    result = AlertDispatcher([transport]).send(Alert(title="Test", message="Body"))

    assert result.ok
    assert result.sent == ("recording",)
    assert transport.alerts[0].title == "Test"
```

### Test SMTP without connecting to an SMTP server

```python
from alert_infra import Alert
from alert_infra.email import SMTPEmailTransport


def test_email_body_redacts_secret():
    calls = []

    def sender(recipients, subject, body, html):
        calls.append((recipients, subject, body, html))

    transport = SMTPEmailTransport(
        host="smtp.example.com",
        from_email="alerts@example.com",
        to_emails=["ops@example.com"],
        sender=sender,
    )

    transport.send(Alert(title="Payment failed", message="Failed", metadata={"api_key": "secret"}))

    assert "secret" not in calls[0][2]
    assert "[REDACTED]" in calls[0][2]
```

### Test webhook transports without network access

```python
from alert_infra import Alert
from alert_infra.apps import SlackWebhookTransport


class MockHttpClient:
    def __init__(self):
        self.calls = []

    def post(self, url, *, json, headers=None, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return 200


def test_slack_payload():
    client = MockHttpClient()
    transport = SlackWebhookTransport("https://hooks.slack.com/services/test", http_client=client)

    transport.send(Alert(title="Test", message="Body", metadata={"authorization": "secret"}))

    assert client.calls[0]["json"]["metadata"]["metadata"]["authorization"] == "[REDACTED]"
```

### Test Django integration

Use Django's in-memory email backend or locmem template loader in tests.

```python
from django.test import override_settings
from alert_infra.django import send_alert


def test_send_alert_disabled_mode():
    with override_settings(ALERT_INFRA={"ENABLED": False, "REDACT_SENSITIVE_DATA": True}):
        result = send_alert(title="Test", message="Body", metadata={"token": "secret"})

    assert result.sent == ()
    assert result.failed == {}
```

## Compatibility namespace

Projects that previously imported from `feature_flag_infra` can continue to use that namespace:

```python
from feature_flag_infra import Alert, AlertDispatcher
from feature_flag_infra.django import send_alert
```

Django settings may also be supplied as `FEATURE_FLAG_INFRA` when `ALERT_INFRA` is not defined. Prefer `ALERT_INFRA` for new projects.

## API reference

### Public imports from `alert_infra`

```python
from alert_infra import (
    Alert,
    AlertConfigurationError,
    AlertDeliveryError,
    AlertDispatcher,
    AlertInfraError,
    AlertTransport,
    AlertValidationError,
    DeliveryResult,
    NoOpTransport,
    REDACTED,
    SENSITIVE_KEYWORDS,
    VALID_SEVERITIES,
    redact_metadata,
)
```

### `Alert`

```python
Alert(
    title: str,
    message: str,
    severity: str = "error",
    source: str | None = None,
    tags: tuple[str, ...] = (),
    metadata: Mapping[str, Any] = {},
    created_at: datetime = <current UTC time>,
    correlation_id: str | None = None,
    request_id: str | None = None,
    redact_sensitive_data: bool = True,
)
```

Methods:

- `to_dict() -> dict[str, Any]`: returns a transport-friendly dictionary with ISO-formatted `created_at`.

### `AlertDispatcher`

```python
AlertDispatcher(
    transports: Sequence[AlertTransport] | None = None,
    *,
    enabled: bool = True,
    raise_on_failure: bool = False,
    logger_: logging.Logger | None = None,
)
```

Methods:

- `send(alert: Alert) -> DeliveryResult`

### Email API

```python
from alert_infra.email import SMTPEmailTransport, format_alert_body, format_alert_subject
```

`SMTPEmailTransport.from_env(prefix="ALERT_SMTP_")` reads SMTP-related environment variables.

### App/webhook API

```python
from alert_infra.apps import SlackWebhookTransport, TelegramBotTransport
```

- `SlackWebhookTransport.from_env(env_var="ALERT_SLACK_WEBHOOK_URL")`
- `TelegramBotTransport.from_env(token_env="ALERT_TELEGRAM_BOT_TOKEN", chat_env="ALERT_TELEGRAM_CHAT_ID")`

### Django API

```python
from alert_infra.django import (
    DjangoEmailTransport,
    build_dispatcher,
    get_alert_infra_settings,
    request_metadata,
    send_alert,
)
```

`send_alert` signature:

```python
send_alert(
    *,
    title: str,
    message: str,
    severity: str | None = None,
    source: str | None = None,
    tags: tuple[str, ...] | list[str] = (),
    metadata: Mapping[str, Any] | None = None,
    request: Any | None = None,
) -> DeliveryResult
```

## Development

Run the test suite:

```bash
pytest
```

Build the package:

```bash
python -m build
```

The project uses `setuptools` and `setuptools-scm` for packaging and dynamic versioning.

## Async alerting with Celery

`alert_infra` can enqueue outbound alert delivery to Celery while keeping the core package framework-independent. Celery is an optional extra; importing `alert_infra` or using the synchronous dispatcher does not import Celery.

Install Celery support when you want queued dispatch:

```bash
pip install "alert-infra[celery]"
```

The async layer serializes an `Alert` with `Alert.to_dict()`, redacts sensitive metadata before queueing, and rehydrates it with `Alert.from_dict()` inside the worker. Transport credentials remain in settings/environment on the worker; they are not passed as task arguments.

### Django Celery setup

Add the task module to your normal Celery autodiscovery path. If your project autodiscovers installed apps, include `alert_infra.django` in `INSTALLED_APPS`; otherwise import `alert_infra.django.tasks` from your Celery app module.

```python
# config/celery.py
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "alert_infra.django",
]

ALERT_INFRA = {
    "ENABLED": True,
    "ASYNC": {
        "ENABLED": True,
        "BACKEND": "celery",
        "TASK_NAME": "alert_infra.dispatch_alert",
        "QUEUE": "alerts",
        "MAX_RETRIES": 3,
        "RETRY_BACKOFF": True,
        "RETRY_BACKOFF_MAX": 300,
        "RETRY_JITTER": True,
        "FAIL_SILENTLY": True,
    },
    "EMAIL": {
        "ENABLED": True,
        "FROM_EMAIL": env("ALERT_FROM_EMAIL"),
        "TO_EMAILS": env.list("ALERT_TO_EMAILS"),
    },
    "SLACK": {
        "ENABLED": True,
        "WEBHOOK_URL": env("ALERT_SLACK_WEBHOOK_URL"),
    },
    "TELEGRAM": {
        "ENABLED": True,
        "BOT_TOKEN": env("ALERT_TELEGRAM_BOT_TOKEN"),
        "CHAT_ID": env("ALERT_TELEGRAM_CHAT_ID"),
    },
}

CELERY_TASK_ROUTES = {
    "alert_infra.dispatch_alert": {"queue": "alerts"},
}
```

Run a worker for the alerts queue:

```bash
celery -A config worker -Q alerts -l info
```

When `ALERT_INFRA["ASYNC"]["ENABLED"]` is true, `alert_infra.django.send_alert(...)` enqueues `alert_infra.dispatch_alert` and returns a `DeliveryResult` with `sent=("celery",)`. When async is disabled, it uses the synchronous `AlertDispatcher` exactly as before. If Celery is unavailable or not configured, `FAIL_SILENTLY=True` returns a failed `DeliveryResult` instead of crashing the request; set `FAIL_SILENTLY=False` to raise a clear configuration error.

### Async settings reference

| Key | Default | Description |
| --- | --- | --- |
| `ENABLED` | `False` | Enable Celery-backed alert dispatch from the Django helper. |
| `BACKEND` | `"celery"` | Async backend. Currently only Celery is supported. |
| `TASK_NAME` | `"alert_infra.dispatch_alert"` | Celery task name to enqueue. |
| `QUEUE` | `"alerts"` | Queue passed to `send_task`/`apply_async`. |
| `MAX_RETRIES` | `3` | Maximum worker retries for retryable transport failures. |
| `RETRY_BACKOFF` | `True` | Use bounded exponential retry countdowns, or an integer base delay. |
| `RETRY_BACKOFF_MAX` | `300` | Maximum retry countdown in seconds. |
| `RETRY_JITTER` | `True` | Randomize retry countdowns to avoid thundering herds. |
| `FAIL_SILENTLY` | `True` | Do not crash web requests when enqueueing fails. |

### Retry and partial-failure behavior

Celery retries are explicit so successful transports are not resent unnecessarily. The task dispatches to all configured transports on the first attempt. If, for example, email succeeds and Slack has a retryable timeout, the retry is scheduled with `transport_names=["slack"]`; email is omitted from the retry. Non-retryable configuration/authentication errors are reported in the task result and are not retried.

Retryable examples include network errors, timeouts, SMTP connection/disconnection failures, SMTP 4xx temporary data errors, and webhook 5xx responses. Non-retryable examples include missing SMTP settings, invalid Slack webhook URLs, invalid Telegram chat IDs/tokens, invalid recipients, authentication/configuration failures, unsupported severities, and webhook 4xx responses.

Task logs and dispatcher logs contain transport names and exception class names only. They do not include webhook URLs, bot tokens, SMTP passwords, raw authorization headers, cookies, or metadata values.

### Plain Python synchronous usage

Plain Python applications can continue using the synchronous dispatcher without Celery:

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.apps import SlackWebhookTransport

sync_dispatcher = AlertDispatcher([SlackWebhookTransport.from_env()])
sync_dispatcher.send(Alert(title="API outage", message="Health checks failed."))
```

### Plain Python Celery usage

Plain Python applications can opt into Celery by passing either a Celery app or a task-like object with `apply_async` to `CeleryAlertDispatcher`:

```python
from celery import Celery
from alert_infra import Alert
from alert_infra.celery import CeleryAlertDispatcher

app = Celery("alerts")
async_dispatcher = CeleryAlertDispatcher(
    celery_app=app,
    config={
        "TASK_NAME": "alert_infra.dispatch_alert",
        "QUEUE": "alerts",
        "MAX_RETRIES": 3,
        "FAIL_SILENTLY": False,
    },
)

async_dispatcher.send(Alert(title="Import failed", message="Supplier import exited with status 1."))
```

For non-Django plain Python workers, define your own Celery task that receives the serialized payload, calls `Alert.from_dict(payload)`, and dispatches with your application-specific `AlertDispatcher`.

### Testing async alerting

Use the repository test suite to exercise serialization, Django settings loading, async enqueueing, task rehydration, retry behavior, partial failures, and transport error classification:

```bash
python -m pytest
```
