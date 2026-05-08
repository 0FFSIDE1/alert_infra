"""Compatibility namespace for projects importing ``feature_flag_infra``."""

from __future__ import annotations

import importlib
import sys

from alert_infra import *  # noqa: F403
from alert_infra import __all__ as _alert_infra_all

_ALIAS_MODULES = (
    "alert",
    "apps",
    "django",
    "email",
    "exceptions",
    "security",
    "transports",
)

for _module_name in _ALIAS_MODULES:
    sys.modules[f"{__name__}.{_module_name}"] = importlib.import_module(f"alert_infra.{_module_name}")

__all__ = list(_alert_infra_all)
