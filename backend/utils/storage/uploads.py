from django.conf import settings

from .factory import get_document_storage


class UploadMissing(Exception):
    pass


class UploadChanged(Exception):
    pass


class StorageUnavailable(Exception):
    pass


def get_upload_provider():
    if settings.NOD_STORAGE_PROVIDER == 'azure':
        from utils.azure.uploads import AzureUploadProvider

        return AzureUploadProvider(get_document_storage())

    if settings.NOD_STORAGE_PROVIDER == 's3':
        from utils.aws.uploads import S3UploadProvider

        return S3UploadProvider(get_document_storage())

    from .local_uploads import LocalUploadProvider

    return LocalUploadProvider(get_document_storage())
