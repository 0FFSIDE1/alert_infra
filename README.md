# alert_infra

`alert_infra` is a reusable alerting infrastructure package for plain Python services and Django projects. It separates framework-agnostic alert domain logic from framework adapters and transport integrations.

## Internal architecture

- `alert_infra.alert`, `alert_infra.security`, `alert_infra.transports`, and `alert_infra.exceptions` contain the framework-agnostic core.
- `alert_infra.email` contains framework-agnostic SMTP email transport implementations.
- `alert_infra.apps` contains app/webhook integrations such as Slack and Telegram.
- `alert_infra.django` contains Django-only settings loading, Django email backend support, request-context extraction, and the `send_alert` helper.

## Features

- Core `Alert` abstraction with severity, source, tags, metadata, timestamps, correlation IDs, and request IDs.
- Dependency-injected transport interface for custom senders.
- Built-in no-op, SMTP email, Django email backend, Slack webhook, and Telegram bot transports.
- Multi-transport `AlertDispatcher` with safe partial-failure handling.
- Automatic sensitive metadata redaction for keys such as `password`, `token`, `secret`, `api_key`, `authorization`, `cookie`, `session`, `csrf`, `access`, `refresh`, and `private_key`.
- Django settings adapter, template-aware Django email transport, and `send_alert` helper that do not affect plain Python imports.
- Compatibility imports and Django settings alias for projects using the `feature_flag_infra` namespace.

## Installation

```bash
pip install alert-infra
```

For Django integration, install Django in your application environment:

```bash
pip install "alert-infra[django]"
```

## Plain Python usage

```python
from alert_infra import Alert, AlertDispatcher
from alert_infra.email import SMTPEmailTransport

transport = SMTPEmailTransport.from_env()
dispatcher = AlertDispatcher([transport])

dispatcher.send(Alert(
    title="Payment failure",
    message="Payment provider returned an error",
    severity="error",
    source="billing-service",
    metadata={"invoice_id": "INV-001"},
))
```

## Django usage

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
        # Optional Django template names for rendered alert emails.
        "SUBJECT_TEMPLATE": "emails/alert_subject.txt",
        "BODY_TEMPLATE": "emails/alert.txt",
        "HTML_TEMPLATE": "emails/alert.html",
        "TEMPLATE_CONTEXT": {"product_name": "Billing"},
    },
    "SLACK": {
        "ENABLED": True,
        "WEBHOOK_URL": env("ALERT_SLACK_WEBHOOK_URL"),
    },
    "TELEGRAM": {
        "ENABLED": False,
        "BOT_TOKEN": env("ALERT_TELEGRAM_BOT_TOKEN"),
        "CHAT_ID": env("ALERT_TELEGRAM_CHAT_ID"),
    },
}
```

```python
from alert_infra.django import send_alert

send_alert(
    title="Suspicious invoice update",
    message="Invoice status transition was blocked",
    severity="warning",
    source="invoice",
    metadata={
        "invoice_id": invoice.id,
        "user_id": request.user.id,
        "authorization": request.headers.get("Authorization"),
    },
    request=request,
)
```

The `authorization` value is redacted before any transport receives the alert.

## Environment variables

```bash
export ALERT_FROM_EMAIL=alerts@example.com
export ALERT_TO_EMAILS=ops@example.com,security@example.com
export ALERT_SMTP_HOST=smtp.example.com
export ALERT_SMTP_PORT=587
export ALERT_SMTP_USERNAME=alerts@example.com
export ALERT_SMTP_PASSWORD='from-secret-manager'
export ALERT_SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...'
export ALERT_TELEGRAM_BOT_TOKEN='123456:telegram-token'
export ALERT_TELEGRAM_CHAT_ID='-1001234567890'
```

## Email setup

Use SMTP in plain Python:

```python
from alert_infra.email import SMTPEmailTransport

email_transport = SMTPEmailTransport.from_env()
```

Use the Django email backend by enabling email without `BACKEND="smtp"` in `ALERT_INFRA`. The package will call Django's configured email backend from the Django adapter.

Django email rendering can use your project templates by setting `SUBJECT_TEMPLATE`, `BODY_TEMPLATE`, and/or `HTML_TEMPLATE` under `ALERT_INFRA["EMAIL"]`. Templates receive `alert`, `alert_dict`, `metadata`, `tags`, and any values from `TEMPLATE_CONTEXT`. If no templates are configured, the transport falls back to the built-in alert subject/body formatting.

Projects that need the `feature_flag_infra` namespace can import the same API from `feature_flag_infra` or `feature_flag_infra.django`. Django settings may also be supplied as `FEATURE_FLAG_INFRA` when `ALERT_INFRA` is not defined.

## Slack setup

```python
from alert_infra.apps import SlackWebhookTransport

slack = SlackWebhookTransport.from_env()
```

Slack webhook URLs must be absolute `https://` URLs.

## Telegram setup

```python
from alert_infra.apps import TelegramBotTransport

telegram = TelegramBotTransport.from_env()
```

Telegram uses `ALERT_TELEGRAM_BOT_TOKEN` and `ALERT_TELEGRAM_CHAT_ID` by default.

## Security and redaction

`Alert` redacts sensitive metadata by default. Nested dictionaries and sequences are traversed recursively. Transport payloads receive the redacted alert data, and the dispatcher logs only transport names and exception classes, not raw exception messages that could contain credentials.

Credentials should come from environment variables, Django settings, or explicit constructor arguments. Do not hardcode credentials in source code.

## Extending with custom transports

Any object with a `name` attribute and `send(alert: Alert) -> None` method can be used:

```python
from alert_infra import Alert, AlertDispatcher

class PagerDutyTransport:
    name = "pagerduty"

    def send(self, alert: Alert) -> None:
        # send alert.to_dict() to your provider
        ...

AlertDispatcher([PagerDutyTransport()]).send(Alert(title="Outage", message="API down"))
```

## Production recommendations

- Keep alert sending on short timeouts.
- Use background jobs for non-critical request paths.
- Configure multiple transports for critical alerts.
- Store secrets in a secret manager or environment variables.
- Keep `REDACT_SENSITIVE_DATA=True` unless you have a thoroughly reviewed alternative.
- Monitor dispatcher failure rates and provider API status.

## Testing

```bash
pytest
```
