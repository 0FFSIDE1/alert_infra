"""Django compatibility namespace for ``feature_flag_infra`` imports."""

from alert_infra.django import *  # noqa: F403
from alert_infra.django import __all__ as _alert_infra_django_all

__all__ = list(_alert_infra_django_all)
