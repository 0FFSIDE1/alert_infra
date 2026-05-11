from __future__ import annotations

from datetime import datetime, timezone

import pytest
from celery.exceptions import Retry
from django.test import override_settings

from alert_infra import Alert, DeliveryResult, REDACTED
from alert_infra.celery import CeleryAlertDispatcher
from alert_infra.django import get_alert_infra_settings, send_alert
from alert_infra.django import tasks as django_tasks
from alert_infra.exceptions import NonRetryableAlertTransportError, RetryableAlertTransportError
from alert_infra.transports import AlertDispatcher


class FakeTask:
    def __init__(self) -> None:
        self.calls = []

    def apply_async(self, *, args, kwargs, queue):
        self.calls.append({"args": args, "kwargs": kwargs, "queue": queue})


class FakeApp:
    def __init__(self) -> None:
        self.calls = []

    def send_task(self, name, *, args, kwargs, queue):
        self.calls.append({"name": name, "args": args, "kwargs": kwargs, "queue": queue})


class RecordingTransport:
    name = "recording"

    def __init__(self) -> None:
        self.alerts = []

    def send(self, alert):
        self.alerts.append(alert)


class RetryableTransport:
    name = "retryable"

    def send(self, alert):
        raise RetryableAlertTransportError("transient token must not leak")


class NonRetryableTransport:
    name = "nonretryable"

    def send(self, alert):
        raise NonRetryableAlertTransportError("bad config secret must not leak")


def test_alert_serializes_rehydrates_datetime_and_redacts_metadata() -> None:
    alert = Alert(
        title="T",
        message="M",
        created_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        metadata={"token": "secret", "items": {"b", "a"}, "object": object()},
        request_id="req-1",
    )

    payload = alert.to_dict()
    rehydrated = Alert.from_dict(payload)

    assert payload["created_at"] == "2026-05-08T12:00:00+00:00"
    assert payload["metadata"]["token"] == REDACTED
    assert payload["metadata"]["items"] == ["a", "b"]
    assert rehydrated.created_at == alert.created_at
    assert rehydrated.correlation_id == alert.correlation_id
    assert rehydrated.request_id == "req-1"


def test_celery_dispatcher_enqueues_sanitized_payload_and_queue() -> None:
    task = FakeTask()
    dispatcher = CeleryAlertDispatcher(task=task, config={"ENABLED": True, "QUEUE": "alerts"})

    result = dispatcher.send(Alert(title="T", message="M", metadata={"authorization": "Bearer secret"}))

    assert result.sent == ("celery",)
    assert task.calls[0]["queue"] == "alerts"
    assert task.calls[0]["args"][0]["metadata"]["authorization"] == REDACTED
    assert "Bearer secret" not in str(task.calls)


def test_celery_dispatcher_supports_plain_python_app_send_task() -> None:
    app = FakeApp()
    dispatcher = CeleryAlertDispatcher(celery_app=app, config={"TASK_NAME": "custom.alert", "QUEUE": "alerts"})

    dispatcher.send(Alert(title="T", message="M"), transport_names=["slack"])

    assert app.calls[0]["name"] == "custom.alert"
    assert app.calls[0]["kwargs"]["transport_names"] == ["slack"]


def test_sync_dispatcher_classifies_retryable_and_non_retryable_failures() -> None:
    recording = RecordingTransport()
    result = AlertDispatcher([recording, RetryableTransport(), NonRetryableTransport()]).send(Alert(title="T", message="M"))

    assert result.sent == ("recording",)
    assert result.retryable == ("retryable",)
    assert result.non_retryable == ("nonretryable",)


def test_task_rehydrates_and_dispatches_selected_transports(monkeypatch) -> None:
    recording = RecordingTransport()

    def fake_build_dispatcher():
        return AlertDispatcher([recording])

    monkeypatch.setattr(django_tasks, "build_dispatcher", fake_build_dispatcher)

    result = django_tasks.dispatch_alert_task.run(Alert(title="T", message="M").to_dict())

    assert result["sent"] == ["recording"]
    assert recording.alerts[0].title == "T"


def test_task_retries_only_retryable_failed_transports(monkeypatch) -> None:
    attempts = []

    class FakeDispatcher:
        def send(self, alert, transport_names=None):
            attempts.append(tuple(transport_names or ()))
            return DeliveryResult(sent=("recording",), failed={"retryable": "RetryableAlertTransportError"}, retryable=("retryable",))

    retry_kwargs = {}

    def fake_retry(**kwargs):
        retry_kwargs.update(kwargs)
        raise Retry("retry")

    monkeypatch.setattr(django_tasks, "build_dispatcher", lambda: FakeDispatcher())
    monkeypatch.setattr(django_tasks.dispatch_alert_task, "retry", fake_retry)
    payload = Alert(title="T", message="M").to_dict()

    with pytest.raises(Retry):
        django_tasks.dispatch_alert_task.run(payload, async_options={"MAX_RETRIES": 3, "RETRY_JITTER": False})

    assert attempts == [()]
    assert retry_kwargs["args"] == [payload]
    assert "alert_payload" not in retry_kwargs["kwargs"]
    assert retry_kwargs["kwargs"]["transport_names"] == ["retryable"]


def test_task_does_not_retry_non_retryable_failures(monkeypatch) -> None:
    class FakeDispatcher:
        def send(self, alert, transport_names=None):
            return DeliveryResult(failed={"nonretryable": "NonRetryableAlertTransportError"}, non_retryable=("nonretryable",))

    monkeypatch.setattr(django_tasks, "build_dispatcher", lambda: FakeDispatcher())

    result = django_tasks.dispatch_alert_task.run(Alert(title="T", message="M").to_dict())

    assert result["failed"] == {"nonretryable": "NonRetryableAlertTransportError"}
    assert result["retryable"] == []


def test_django_settings_load_async_config() -> None:
    with override_settings(ALERT_INFRA={"ASYNC": {"ENABLED": True, "QUEUE": "alerts"}}):
        cfg = get_alert_infra_settings()

    assert cfg["ASYNC"]["ENABLED"] is True
    assert cfg["ASYNC"]["QUEUE"] == "alerts"
    assert cfg["ASYNC"]["MAX_RETRIES"] == 3


def test_django_send_alert_uses_celery_when_enabled(monkeypatch) -> None:
    task = FakeTask()
    monkeypatch.setattr("alert_infra.django.config.CeleryAlertDispatcher", lambda config: CeleryAlertDispatcher(task=task, config=config))

    with override_settings(ALERT_INFRA={"ENABLED": True, "ASYNC": {"ENABLED": True, "QUEUE": "alerts", "FAIL_SILENTLY": False}}):
        result = send_alert(title="T", message="M", metadata={"cookie": "secret"})

    assert result.sent == ("celery",)
    assert task.calls[0]["queue"] == "alerts"
    assert task.calls[0]["args"][0]["metadata"]["cookie"] == REDACTED


def test_django_send_alert_sends_synchronously_when_async_disabled() -> None:
    with override_settings(ALERT_INFRA={"ENABLED": False, "ASYNC": {"ENABLED": False}}):
        result = send_alert(title="T", message="M")

    assert result.sent == ()


def test_celery_enqueue_failure_respects_fail_silently() -> None:
    class BrokenTask:
        def apply_async(self, *, args, kwargs, queue):
            raise RuntimeError("broker password secret")

    dispatcher = CeleryAlertDispatcher(task=BrokenTask(), config={"FAIL_SILENTLY": True})

    result = dispatcher.send(Alert(title="T", message="M"))

    assert result.failed == {"celery": "RuntimeError"}


def test_task_respects_max_retries(monkeypatch) -> None:
    class FakeDispatcher:
        def send(self, alert, transport_names=None):
            return DeliveryResult(failed={"retryable": "RetryableAlertTransportError"}, retryable=("retryable",))

    def fail_retry(**kwargs):  # pragma: no cover - should not be called once max retries is exhausted.
        raise AssertionError("retry should not be scheduled")

    monkeypatch.setattr(django_tasks, "build_dispatcher", lambda: FakeDispatcher())
    monkeypatch.setattr(django_tasks.dispatch_alert_task, "retry", fail_retry)

    # Celery's bound task proxy exposes the current request internally; direct
    # unit calls cannot reliably mutate it, so max_retries=0 exercises the same
    # exhausted branch without enqueueing another retry.
    result = django_tasks.dispatch_alert_task.run(Alert(title="T", message="M").to_dict(), async_options={"MAX_RETRIES": 0})

    assert result["retryable"] == ["retryable"]
