SECRET_KEY = "tests-secret-key"
INSTALLED_APPS = []
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "alerts@example.com"
USE_TZ = True
ALERT_INFRA = {"ENABLED": False}
