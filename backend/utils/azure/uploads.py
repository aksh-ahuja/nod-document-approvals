from azure.core import MatchConditions
from azure.core.exceptions import AzureError, ResourceModifiedError, ResourceNotFoundError

from utils.storage.uploads import StorageUnavailable, UploadChanged, UploadMissing


class AzureUploadProvider:
    def __init__(self, storage):
        self.storage = storage

    def sign(self, upload, expires_in):
        try:
            url = self.storage.url(
                upload.staging_key,
                expire=expires_in,
                mode='c',
                parameters={'protocol': 'https'},
            )
        except AzureError as error:
            raise StorageUnavailable from error

        return {
            'upload_url': url,
            'method': 'PUT',
            'headers': {'Content-Type': upload.content_type, 'x-ms-blob-type': 'BlockBlob'},
            'local': False,
        }

    def inspect(self, key):
        try:
            blob = self.storage.client.get_blob_client(key)
            properties = blob.get_blob_properties()
        except ResourceNotFoundError as error:
            raise UploadMissing from error
        except AzureError as error:
            raise StorageUnavailable from error

        return {'size': properties.size, 'etag': properties.etag}

    def read(self, key, etag, limit):
        try:
            blob = self.storage.client.get_blob_client(key)
            return blob.download_blob(
                etag=etag,
                match_condition=MatchConditions.IfNotModified,
                offset=0,
                length=limit + 1,
                max_concurrency=1,
            ).readall()
        except ResourceModifiedError as error:
            raise UploadChanged from error
        except ResourceNotFoundError as error:
            raise UploadMissing from error
        except AzureError as error:
            raise StorageUnavailable from error
