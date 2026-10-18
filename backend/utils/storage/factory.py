from django.conf import settings
from django.core.files.storage import storages
from django.utils.http import content_disposition_header


def get_document_storage():
    return storages['documents']


def get_cloud_file_url(key, filename, content_type, download, expires_in):
    disposition = content_disposition_header(download, filename)

    if settings.NOD_STORAGE_PROVIDER == 'azure':
        parameters = {
            'content_type': content_type,
            'content_disposition': disposition,
            'cache_control': 'private, no-store',
        }
    else:
        parameters = {
            'ResponseContentType': content_type,
            'ResponseContentDisposition': disposition,
            'ResponseCacheControl': 'private, no-store',
        }

    return get_document_storage().url(key, parameters=parameters, expire=expires_in)
