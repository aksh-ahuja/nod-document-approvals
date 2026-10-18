import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from nod_auth_service.models import User
from nod_upload_service.constants import UPLOAD_ACTIVE_LIMIT, UPLOAD_MAX_ATTEMPTS
from nod_upload_service.models import DocumentUpload
from nod_submission_service.models import Submission
from nod_upload_service.services.generic_upload_worker_service import GenericUploadWorkerService
from utils.storage.factory import get_document_storage
from utils.storage.uploads import StorageUnavailable, get_upload_provider


class DirectUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            'upload@example.com', name='Owner', email_verified=True
        )
        cls.other = User.objects.create_user(
            'other-upload@example.com', name='Other', email_verified=True
        )
        cls.reviewer = User.objects.create_user(
            'upload-reviewer@example.com', name='Reviewer', email_verified=True, can_review=True
        )

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        config = override_settings(
            DEBUG=True,
            NOD_STORAGE_PROVIDER='local',
            STORAGES={
                'documents': {
                    'BACKEND': 'django.core.files.storage.FileSystemStorage',
                    'OPTIONS': {'location': directory.name},
                }
            },
        )
        config.enable()
        self.addCleanup(config.disable)
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.storage = get_document_storage()

    def intent(self, size=6):
        response = self.client.post(
            '/api/v1/uploads/create/',
            {
                'filename': 'notes.txt',
                'size': size,
                'content_type': 'text/html',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn('no-store', response['Cache-Control'])

        return response.data['data']

    def transfer(self, instruction, content=b'hello!'):
        return self.client.put(instruction['upload_url'], content, content_type='text/plain')

    def complete(self, instruction):
        return self.client.post(f'/api/v1/uploads/complete/{instruction["upload_id"]}/')

    def queued(self):
        instruction = self.intent()
        self.assertEqual(self.transfer(instruction).status_code, 201)
        self.assertEqual(self.complete(instruction).status_code, 202)

        return instruction

    def submit(self, instruction, request_id=None):
        return self.client.post(
            '/api/v1/submissions/create/',
            {
                'title': 'Direct upload',
                'reviewer_id': str(self.reviewer.public_id),
                'upload_id': instruction['upload_id'],
                'client_request_id': str(request_id or uuid.uuid4()),
            },
            format='json',
        )

    def test_validate_then_attach_and_retry(self):
        instruction = self.queued()
        self.assertEqual(self.submit(instruction).status_code, 409)
        self.assertFalse(Submission.objects.exists())
        self.assertEqual(list(Path(self.storage.location).glob('documents/**/*')), [])
        self.assertTrue(GenericUploadWorkerService.run_once())
        key = uuid.uuid4()
        first = self.submit(instruction, key)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['data']['file']['content_type'], 'text/plain')
        self.assertEqual(self.submit(instruction, key).status_code, 200)
        self.assertEqual(self.submit(instruction).status_code, 409)
        self.assertEqual(Submission.objects.count(), 1)
        self.assertFalse(GenericUploadWorkerService.run_once())

    def test_complete_is_idempotent_and_does_not_read_bytes(self):
        instruction = self.intent()
        self.transfer(instruction)

        with patch('utils.storage.local_uploads.LocalUploadProvider.read') as read:
            self.assertEqual(self.complete(instruction).status_code, 202)
            self.assertEqual(self.complete(instruction).data['data']['status'], 'validating')
            read.assert_not_called()

        GenericUploadWorkerService.run_once()
        self.assertEqual(self.complete(instruction).data['data']['status'], 'ready')
        self.assertEqual(DocumentUpload.objects.get().attempts, 1)

    def test_foreign_upload_cannot_be_written_completed_read_or_attached(self):
        instruction = self.queued()
        GenericUploadWorkerService.run_once()
        self.client.force_login(self.other)
        self.assertEqual(self.transfer(instruction).status_code, 404)
        self.assertEqual(self.complete(instruction).status_code, 404)
        self.assertEqual(self.submit(instruction).status_code, 404)
        self.assertEqual(
            self.client.get(f'/api/v1/uploads/status/{instruction["upload_id"]}/').status_code, 404
        )

    def test_local_token_is_required_expires_and_cannot_be_reused(self):
        instruction = self.intent()
        self.assertEqual(
            self.client.put(
                instruction['upload_url'] + 'tampered', b'hello!', content_type='text/plain'
            ).status_code,
            403,
        )
        self.assertEqual(self.transfer(instruction).status_code, 201)
        self.assertEqual(self.transfer(instruction).status_code, 409)
        DocumentUpload.objects.update(upload_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.complete(instruction).status_code, 410)

    def test_local_upload_disabled_for_cloud_and_production(self):
        instruction = self.intent()

        for options in ({'DEBUG': False}, {'NOD_STORAGE_PROVIDER': 'azure'}):
            with override_settings(**options):
                self.assertEqual(self.transfer(instruction).status_code, 404)

    def test_missing_and_wrong_size_can_never_be_attached(self):
        instruction = self.intent()
        self.assertEqual(self.complete(instruction).status_code, 409)
        upload = DocumentUpload.objects.get()
        self.storage.save(upload.staging_key, ContentFile(b'too much content'))
        self.assertEqual(self.complete(instruction).status_code, 400)
        self.assertEqual(self.submit(instruction).status_code, 409)

    def test_staging_change_after_completion_is_rejected(self):
        instruction = self.queued()
        upload = DocumentUpload.objects.get()
        Path(self.storage.path(upload.staging_key)).write_bytes(b'changed bytes')
        GenericUploadWorkerService.run_once()
        upload.refresh_from_db()
        self.assertEqual(upload.status, 'rejected')
        self.assertEqual(upload.final_key, '')
        self.assertEqual(self.submit(instruction).status_code, 409)

    def test_staging_replacement_after_validation_cannot_change_document(self):
        instruction = self.queued()
        GenericUploadWorkerService.run_once()
        upload = DocumentUpload.objects.get()
        Path(self.storage.path(upload.staging_key)).write_bytes(b'evil!!')
        self.assertEqual(self.submit(instruction).status_code, 201)

        with self.storage.open(Submission.objects.get().file_key) as file:
            self.assertEqual(file.read(), b'hello!')

    def test_invalid_content_is_rejected_by_worker(self):
        instruction = self.intent()
        self.transfer(instruction, b'abc\x00de')
        self.complete(instruction)
        GenericUploadWorkerService.run_once()
        upload = DocumentUpload.objects.get()
        self.assertEqual(upload.status, 'rejected')
        self.assertTrue(upload.error)
        self.assertEqual(self.submit(instruction).status_code, 409)

    def test_transient_failure_retries_and_exhausts(self):
        self.queued()

        with patch(
            'utils.storage.local_uploads.LocalUploadProvider.read', side_effect=StorageUnavailable
        ):
            for attempt in range(UPLOAD_MAX_ATTEMPTS):
                self.assertTrue(GenericUploadWorkerService.run_once())
                upload = DocumentUpload.objects.get()
                self.assertEqual(upload.attempts, attempt + 1)

                if attempt < UPLOAD_MAX_ATTEMPTS - 1:
                    self.assertEqual(upload.status, 'validating')
                    self.assertFalse(GenericUploadWorkerService.run_once())
                    DocumentUpload.objects.update(next_attempt_at=timezone.now())

        self.assertEqual(DocumentUpload.objects.get().status, 'rejected')

    def test_expired_lease_can_be_reclaimed_but_stale_worker_cannot_publish(self):
        self.queued()
        first = GenericUploadWorkerService.claim()
        self.assertIsNotNone(first)
        self.assertIsNone(GenericUploadWorkerService.claim())
        DocumentUpload.objects.update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        second = GenericUploadWorkerService.claim()
        self.assertNotEqual(first.lease_token, second.lease_token)
        GenericUploadWorkerService._GenericUploadWorkerService__validate(first)
        self.assertEqual(DocumentUpload.objects.get().status, 'validating')
        GenericUploadWorkerService._GenericUploadWorkerService__validate(second)
        upload = DocumentUpload.objects.get()
        self.assertEqual(upload.status, 'ready')
        self.assertEqual(len(list(Path(self.storage.location).rglob('*.txt'))), 1)

    def test_cleanup_removes_abandoned_and_orphan_objects_but_keeps_attached_file(self):
        instruction = self.queued()
        GenericUploadWorkerService.run_once()
        self.submit(instruction)
        upload = DocumentUpload.objects.get()
        orphan = self.storage.save(
            f'documents/{upload.public_id}/orphan.txt', ContentFile(b'orphan')
        )
        DocumentUpload.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        GenericUploadWorkerService.cleanup()
        self.assertFalse(self.storage.exists(upload.staging_key))
        self.assertFalse(self.storage.exists(orphan))
        self.assertTrue(self.storage.exists(upload.final_key))
        self.assertEqual(DocumentUpload.objects.get().status, 'attached')

        self.queued()
        GenericUploadWorkerService.run_once()
        abandoned = DocumentUpload.objects.get(status='ready')
        DocumentUpload.objects.filter(pk=abandoned.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        GenericUploadWorkerService.cleanup()
        self.assertFalse(self.storage.exists(abandoned.final_key))
        self.assertFalse(self.storage.exists(abandoned.staging_key))
        abandoned.refresh_from_db()
        self.assertEqual(abandoned.status, 'expired')

    def test_quota_and_expired_ready_upload(self):
        instruction = self.queued()
        GenericUploadWorkerService.run_once()
        DocumentUpload.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.submit(instruction).status_code, 410)

        for _ in range(UPLOAD_ACTIVE_LIMIT):
            self.intent()

        response = self.client.post(
            '/api/v1/uploads/create/',
            {
                'filename': 'notes.txt',
                'size': 6,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 429)

    def test_arbitrary_paths_and_legacy_file_bodies_are_not_accepted(self):
        response = self.client.post(
            '/api/v1/submissions/create/',
            {
                'title': 'Bad reference',
                'reviewer_id': str(self.reviewer.public_id),
                'client_request_id': str(uuid.uuid4()),
                'file_key': 'documents/someone-else.pdf',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.post(
                '/api/v1/submissions/create/',
                {
                    'file': 'bytes',
                },
                format='multipart',
            ).status_code,
            415,
        )

    def test_csrf_required_for_signing_and_local_put(self):
        instruction = self.intent()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(
            client.post(
                '/api/v1/uploads/create/',
                {
                    'filename': 'notes.txt',
                    'size': 6,
                },
                format='json',
            ).status_code,
            403,
        )
        self.assertEqual(
            client.put(instruction['upload_url'], b'hello!', content_type='text/plain').status_code,
            403,
        )

    def test_failed_signing_returns_retryable_error(self):
        with patch(
            'utils.storage.local_uploads.LocalUploadProvider.sign', side_effect=StorageUnavailable
        ):
            response = self.client.post(
                '/api/v1/uploads/create/',
                {
                    'filename': 'notes.txt',
                    'size': 6,
                },
                format='json',
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(DocumentUpload.objects.get().status, 'rejected')
