import os

from django.core.exceptions import ImproperlyConfigured


def document_storage_config(provider, debug, base_dir):
    if provider == 'local':
        if not debug:
            raise ImproperlyConfigured('Use Azure or S3 document storage in production.')

        return {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
            'OPTIONS': {
                'location': os.getenv('NOD_UPLOAD_ROOT', str(base_dir / 'private_uploads')),
                'file_permissions_mode': 0o600,
                'directory_permissions_mode': 0o700,
            },
        }

    if provider == 'azure':
        account = os.getenv('NOD_AZURE_STORAGE_ACCOUNT', '')
        container = os.getenv('NOD_AZURE_STORAGE_CONTAINER', '')
        connection = os.getenv('NOD_AZURE_STORAGE_CONNECTION_STRING', '')

        if not container or not (account or connection):
            raise ImproperlyConfigured(
                'Set the Azure storage account and private container for documents.'
            )

        options = {
            'azure_container': container,
            'overwrite_files': False,
            'object_parameters': {
                'content_disposition': 'attachment',
                'content_type': 'application/octet-stream',
                'cache_control': 'private, no-store',
            },
        }

        if connection:
            options['connection_string'] = connection
        else:
            from azure.identity import DefaultAzureCredential

            options['account_name'] = account
            options['token_credential'] = DefaultAzureCredential(
                managed_identity_client_id=os.getenv('AZURE_CLIENT_ID') or None
            )

        return {'BACKEND': 'storages.backends.azure_storage.AzureStorage', 'OPTIONS': options}

    if provider == 's3':
        bucket = os.getenv('NOD_S3_BUCKET', '')

        if not bucket:
            raise ImproperlyConfigured('Set NOD_S3_BUCKET to a private document bucket.')

        return {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': bucket,
                'region_name': os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
                'default_acl': None,
                'file_overwrite': False,
                'querystring_auth': True,
                'signature_version': 's3v4',
                'max_memory_size': 2 * 1024 * 1024,
                'object_parameters': {
                    'ContentDisposition': 'attachment',
                    'ContentType': 'application/octet-stream',
                    'CacheControl': 'private, no-store',
                },
            },
        }

    raise ImproperlyConfigured('NOD_STORAGE_PROVIDER must be local, azure, or s3.')
