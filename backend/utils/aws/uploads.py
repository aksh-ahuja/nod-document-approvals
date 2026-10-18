from botocore.exceptions import BotoCoreError, ClientError

from utils.storage.uploads import StorageUnavailable, UploadChanged, UploadMissing


class S3UploadProvider:
    def __init__(self, storage):
        self.storage = storage
        self.client = storage.connection.meta.client

    def sign(self, upload, expires_in):
        try:
            url = self.client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.storage.bucket_name,
                    'Key': upload.staging_key,
                    'ContentType': upload.content_type,
                },
                ExpiresIn=expires_in,
                HttpMethod='PUT',
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailable from error

        return {
            'upload_url': url,
            'method': 'PUT',
            'headers': {'Content-Type': upload.content_type},
            'local': False,
        }

    def inspect(self, key):
        try:
            properties = self.client.head_object(Bucket=self.storage.bucket_name, Key=key)
        except ClientError as error:
            self.__raise_storage_error(error)
        except BotoCoreError as error:
            raise StorageUnavailable from error

        return {'size': properties['ContentLength'], 'etag': properties['ETag']}

    def read(self, key, etag, limit):
        try:
            response = self.client.get_object(
                Bucket=self.storage.bucket_name,
                Key=key,
                IfMatch=etag,
                Range=f'bytes=0-{limit}',
            )
            body = response['Body']

            try:
                return body.read(limit + 1)
            finally:
                body.close()
        except ClientError as error:
            self.__raise_storage_error(error)
        except BotoCoreError as error:
            raise StorageUnavailable from error

    @staticmethod
    def __raise_storage_error(error):
        code = error.response.get('Error', {}).get('Code')

        if code in ('404', 'NoSuchKey', 'NotFound'):
            raise UploadMissing from error

        if code in ('412', 'PreconditionFailed'):
            raise UploadChanged from error

        raise StorageUnavailable from error
