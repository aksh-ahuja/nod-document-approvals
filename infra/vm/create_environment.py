"""Run as root on the VM; generate production secrets without printing them."""

import os
from pathlib import Path
import secrets

directory = Path('/opt/nod/shared')
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
production = directory / 'production.env'
database = directory / 'database.env'
if production.exists() or database.exists():
    if not production.exists() or not database.exists():
        raise SystemExit('Incomplete existing environment; refusing to replace secrets.')
    print('Existing production secrets preserved.')
else:
    app_password = secrets.token_hex(32)
    settings = {
        'NOD_DEBUG': 'false',
        'NOD_SECRET_KEY': secrets.token_urlsafe(64),
        'NOD_ALLOWED_HOSTS': 'nod.haggle.site,localhost,127.0.0.1',
        'NOD_CSRF_TRUSTED_ORIGINS': 'https://nod.haggle.site',
        'NOD_TRUSTED_PROXY_IPS': '172.29.80.1',
        'NOD_COOKIE_SECURE': 'true',
        'NOD_ENABLE_DEMO': 'false',
        'NOD_DB_ENGINE': 'postgresql',
        'NOD_DB_HOST': 'db',
        'NOD_DB_PORT': '5432',
        'NOD_DB_NAME': 'nod',
        'NOD_DB_USER': 'nod',
        'NOD_DB_PASSWORD': app_password,
        'NOD_DB_SSLMODE': 'disable',
        'NOD_STORAGE_PROVIDER': 'azure',
        'NOD_AZURE_STORAGE_ACCOUNT': 'voicemodelb',
        'NOD_AZURE_STORAGE_CONTAINER': 'nod-production-documents',
        'NOD_AZURE_STORAGE_CONNECTION_STRING': '',
        'NOD_EMAIL_PROVIDER': 'azure',
        'NOD_EMAIL_SENDER': 'DoNotReply@30e6ac1b-d862-4375-9ff9-272cd5dc98c0.azurecomm.net',
        'NOD_AZURE_EMAIL_ENDPOINT': 'https://folio-comm.india.communication.azure.com',
        'NOD_AZURE_EMAIL_CONNECTION_STRING': '',
        'NOD_LIBREOFFICE_BINARY': 'soffice',
    }
    database_settings = {
        'POSTGRES_DB': 'nod',
        'POSTGRES_USER': 'nod_admin',
        'POSTGRES_PASSWORD': secrets.token_hex(32),
        'NOD_APP_DB_PASSWORD': app_password,
    }
    for path, values in ((production, settings), (database, database_settings)):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    print('Production environment created with mode 0600; Azure uses managed identity.')
