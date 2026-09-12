from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Desactiva HTTPS forzado en desarrollo
SECURE_SSL_REDIRECT = False
