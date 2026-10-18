import io
import sys
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from utils.storage.uploads import UploadChanged, UploadMissing


class CloudUploadProviderTests(TestCase):
    def azure_provider(self):
        try:
            module = import_module('utils.azure.uploads')
        except ModuleNotFoundError:

            class AzureError(Exception):
                pass

            class ResourceModifiedError(AzureError):
                pass

            class ResourceNotFoundError(AzureError):
                pass

            with patch.dict(
                sys.modules,
                {
                    'azure.core': SimpleNamespace(
                        MatchConditions=SimpleNamespace(IfNotModified='etag')
                    ),
                    'azure.core.exceptions': SimpleNamespace(
                        AzureError=AzureError,
                        ResourceModifiedError=ResourceModifiedError,
                        ResourceNotFoundError=ResourceNotFoundError,
                    ),
                },
            ):
                module = import_module('utils.azure.uploads')

        storage = MagicMock()

        return module.AzureUploadProvider(storage), storage, module

    def s3_provider(self):
        try:
            module = import_module('utils.aws.uploads')
        except ModuleNotFoundError:

            class ClientError(Exception):
                def __init__(self, response, operation):
                    self.response = response

            with patch.dict(
                sys.modules,
                {
                    'botocore.exceptions': SimpleNamespace(
                        BotoCoreError=type('BotoCoreError', (Exception,), {}),
                        ClientError=ClientError,
                    )
                },
            ):
                module = import_module('utils.aws.uploads')

        storage = MagicMock(bucket_name='private-documents')

        return module.S3UploadProvider(storage), storage, module

    def test_azure_signing_only_allows_creating_the_staging_blob(self):
        provider, storage, _ = self.azure_provider()
        storage.url.return_value = 'https://storage.example/staging/key?signature'
        result = provider.sign(
            SimpleNamespace(staging_key='staging/key', content_type='text/plain'), 300
        )
        storage.url.assert_called_once_with(
            'staging/key', expire=300, mode='c', parameters={'protocol': 'https'}
        )
        self.assertEqual(result['method'], 'PUT')
        self.assertEqual(result['headers']['x-ms-blob-type'], 'BlockBlob')
        self.assertFalse(result['local'])

    def test_azure_reads_are_bounded_and_pinned_to_the_completed_etag(self):
        provider, storage, module = self.azure_provider()
        blob = storage.client.get_blob_client.return_value
        blob.download_blob.return_value.readall.return_value = b'hello'
        self.assertEqual(provider.read('staging/key', 'etag-1', 10), b'hello')
        blob.download_blob.assert_called_once_with(
            etag='etag-1',
            match_condition=module.MatchConditions.IfNotModified,
            offset=0,
            length=11,
            max_concurrency=1,
        )
        blob.download_blob.side_effect = module.ResourceModifiedError('changed')

        with self.assertRaises(UploadChanged):
            provider.read('staging/key', 'etag-1', 10)

    def test_s3_signature_targets_one_key_and_content_type(self):
        provider, storage, _ = self.s3_provider()
        provider.sign(
            SimpleNamespace(staging_key='staging/key', content_type='application/pdf'), 300
        )
        storage.connection.meta.client.generate_presigned_url.assert_called_once_with(
            'put_object',
            Params={
                'Bucket': 'private-documents',
                'Key': 'staging/key',
                'ContentType': 'application/pdf',
            },
            ExpiresIn=300,
            HttpMethod='PUT',
        )

    def test_s3_reads_are_bounded_and_reject_replaced_objects(self):
        provider, storage, module = self.s3_provider()
        client = storage.connection.meta.client
        body = io.BytesIO(b'hello')
        client.get_object.return_value = {'Body': body}
        self.assertEqual(provider.read('staging/key', 'etag-1', 10), b'hello')
        self.assertTrue(body.closed)
        client.get_object.assert_called_once_with(
            Bucket='private-documents', Key='staging/key', IfMatch='etag-1', Range='bytes=0-10'
        )
        client.get_object.side_effect = module.ClientError(
            {'Error': {'Code': 'PreconditionFailed'}}, 'GetObject'
        )

        with self.assertRaises(UploadChanged):
            provider.read('staging/key', 'etag-1', 10)

        client.head_object.side_effect = module.ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )

        with self.assertRaises(UploadMissing):
            provider.inspect('staging/key')
