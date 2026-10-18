import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

engine = os.getenv('NOD_DB_ENGINE', 'postgresql')
if engine == 'sqlite':
    if os.getenv('NOD_DEBUG', 'false').lower() != 'true':
        raise ImproperlyConfigured('SQLite is only supported for local development.')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv(
                'NOD_SQLITE_PATH', str(Path(__file__).resolve().parent.parent / 'nod.sqlite3')
            ),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('NOD_DB_NAME', 'nod'),
            'USER': os.getenv('NOD_DB_USER', 'nod'),
            'PASSWORD': os.getenv('NOD_DB_PASSWORD', ''),
            'HOST': os.getenv('NOD_DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('NOD_DB_PORT', '5432'),
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {'sslmode': os.getenv('NOD_DB_SSLMODE', 'require')},
        }
    }
