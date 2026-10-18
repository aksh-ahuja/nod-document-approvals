import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('NOD_DEBUG', 'false').lower() == 'true'
SECRET_KEY = os.getenv('NOD_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Set NOD_SECRET_KEY before starting Nod.')
    SECRET_KEY = 'nod-local-development-key-do-not-use-in-production'
if not DEBUG and (
    len(SECRET_KEY) < 50 or SECRET_KEY.startswith(('replace-', 'local-', 'nod-local-'))
):
    raise ImproperlyConfigured(
        'Production requires a unique random NOD_SECRET_KEY of at least 50 characters.'
    )
ALLOWED_HOSTS = os.getenv('NOD_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = list(filter(None, os.getenv('NOD_CSRF_TRUSTED_ORIGINS', '').split(',')))
NOD_TRUSTED_PROXY_IPS = set(filter(None, os.getenv('NOD_TRUSTED_PROXY_IPS', '').split(',')))
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'nod_auth_service',
    'nod_submission_service',
    'nod_upload_service',
]
MIDDLEWARE = [
    'utils.proxy.TrustedProxyMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'nod_central_service.urls'
WSGI_APPLICATION = 'nod_central_service.wsgi.application'
AUTH_USER_MODEL = 'nod_auth_service.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'UTC'
LANGUAGE_CODE = 'en-us'
from .database import DATABASES
from .rest import REST_FRAMEWORK

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
SESSION_COOKIE_NAME = 'nod_session'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SESSION_COOKIE_SECURE = os.getenv('NOD_COOKIE_SECURE', str(not DEBUG)).lower() == 'true'
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_FAILURE_VIEW = 'utils.helpers.csrf_failure'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
NOD_STORAGE_PROVIDER = os.getenv('NOD_STORAGE_PROVIDER', 'local' if DEBUG else 'azure')
from .storage import document_storage_config

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    'documents': document_storage_config(NOD_STORAGE_PROVIDER, DEBUG, BASE_DIR),
}
NOD_LIBREOFFICE_BINARY = os.getenv('NOD_LIBREOFFICE_BINARY', 'soffice')
NOD_PREVIEW_TIMEOUT = 30
NOD_PREVIEW_MAX_BYTES = 20 * 1024 * 1024
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
NOD_EMAIL_PROVIDER = os.getenv('NOD_EMAIL_PROVIDER', 'azure')
NOD_EMAIL_SENDER = os.getenv('NOD_EMAIL_SENDER', '')
NOD_AZURE_EMAIL_ENDPOINT = os.getenv('NOD_AZURE_EMAIL_ENDPOINT', '')
NOD_AZURE_EMAIL_CONNECTION_STRING = os.getenv('NOD_AZURE_EMAIL_CONNECTION_STRING', '')
NOD_ENABLE_DEMO = DEBUG and os.getenv('NOD_ENABLE_DEMO', 'false').lower() == 'true'
if NOD_EMAIL_PROVIDER == 'console' and not DEBUG:
    raise ImproperlyConfigured('Console email is allowed only with NOD_DEBUG=true.')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {'azure': {'level': 'WARNING'}},
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
    }
]
SPECTACULAR_SETTINGS = {
    'TITLE': 'Nod API',
    'DESCRIPTION': 'Document submission and review. Use auth/login/ first; Swagger automatically sends the session cookie and current CSRF token. Local demo accounts use NodDemo!2026; production requires your registered account. Signed file URLs expire after five minutes.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SERVE_AUTHENTICATION': [],
    'COMPONENT_SPLIT_REQUEST': True,
    'SERVERS': [{'url': '/'}],
    'ENUM_NAME_OVERRIDES': {
        'SubmissionStatus': [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        'SubmissionFilterStatus': ['pending', 'approved', 'rejected'],
        'UploadStatus': ['pending', 'validating', 'ready', 'rejected', 'attached', 'expired'],
    },
    'PARSER_WHITELIST': ['rest_framework.parsers.JSONParser'],
}
