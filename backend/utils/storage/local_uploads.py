from pathlib import Path
from urllib.parse import urlencode

from django.core import signing
from django.urls import reverse

from nod_upload_service.constants import UPLOAD_TOKEN_SALT

from .uploads import UploadMissing, UploadChanged


class LocalUploadProvider:
    def __init__(self, storage):
        self.storage = storage

    def sign(self, upload, expires_in):
        token = signing.dumps(
            {'upload_id': str(upload.public_id), 'owner_id': upload.owner_id},
            salt=UPLOAD_TOKEN_SALT,
        )
        path = reverse('nod-local-upload', kwargs={'id': upload.public_id})

        return {
            'upload_url': f'{path}?{urlencode({"token": token})}',
            'method': 'PUT',
            'headers': {'Content-Type': upload.content_type},
            'local': True,
        }

    def inspect(self, key):
        try:
            stat = self.storage.path(key)
            details = Path(stat).stat()
        except FileNotFoundError as error:
            raise UploadMissing from error

        return {'size': details.st_size, 'etag': f'{details.st_mtime_ns}:{details.st_size}'}

    def read(self, key, etag, limit):
        if self.inspect(key)['etag'] != etag:
            raise UploadChanged

        with self.storage.open(key, 'rb') as source:
            content = source.read(limit + 1)

        if self.inspect(key)['etag'] != etag:
            raise UploadChanged

        return content
