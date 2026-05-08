"""Security helpers for redacting sensitive alert metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass, asdict
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEYWORDS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "authorization",
        "cookie",
        "session",
        "csrf",
        "access",
        "refresh",
        "private_key",
    }
)


def is_sensitive_key(key: object) -> bool:
    """Return True when a metadata key name looks sensitive."""
    normalized = str(key).lower().replace("-", "_")
    return any(keyword in normalized for keyword in SENSITIVE_KEYWORDS)


def redact_value(value: Any) -> Any:
    """Return a JSON-friendly redacted copy of ``value``.

    Nested mappings and sequences are traversed recursively. Unsupported values are
    converted to strings so transports can serialize payloads consistently without
    leaking object internals through reprs that may contain secrets.
    """
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(key) else redact_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)

    if isinstance(value, list):
        return [redact_value(item) for item in value]

    if isinstance(value, set):
        return sorted(redact_value(item) for item in value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]

    return str(value)


def redact_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Redact sensitive fields from metadata and return a new dictionary."""
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    return redact_value(metadata)
