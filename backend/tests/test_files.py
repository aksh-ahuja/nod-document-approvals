import io
import hashlib
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch
from unittest import skipUnless
from zipfile import ZipFile

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from nod_auth_service.models import User
from nod_submission_service.constants import FILE_LINK_TTL
from nod_upload_service.constants import FILE_MAX_BYTES
from nod_upload_service.models import DocumentUpload
from nod_submission_service.models import Submission, SubmissionEvent
from nod_upload_service.services.generic_upload_worker_service import GenericUploadWorkerService
from utils.storage.factory import get_document_storage
from utils.storage.preview import PreviewUnavailable

PDF = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'


def docx_file(extra=None):
    output = io.BytesIO()

    with ZipFile(output, 'w') as archive:
        archive.writestr(
            '[Content_Types].xml',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            '_rels/.rels',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            'word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Review this proposal.</w:t></w:r></w:p></w:body></w:document>',
        )

        for name, content in (extra or {}).items():
            archive.writestr(name, content)

    return SimpleUploadedFile('proposal.docx', output.getvalue())


class DocumentFileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            'file-owner@example.com', name='Owner', email_verified=True
        )
        cls.reviewer = User.objects.create_user(
            'file-reviewer@example.com', name='Reviewer', can_review=True, email_verified=True
        )
        cls.other = User.objects.create_user(
            'file-other@example.com', name='Other', can_review=True, email_verified=True
        )

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = override_settings(
            DEBUG=True,
            NOD_STORAGE_PROVIDER='local',
            STORAGES={
                'documents': {
                    'BACKEND': 'django.core.files.storage.FileSystemStorage',
                    'OPTIONS': {'location': self.directory.name},
                },
            },
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.request_id = str(uuid.uuid4())
        self.uploads = {}

    def upload(self, file=None, **fields):
        file = file or SimpleUploadedFile('proposal.pdf', PDF, content_type='text/html')
        content = file.read()
        key = (file.name, hashlib.sha256(content).hexdigest())

        if key not in self.uploads:
            response = self.client.post(
                '/api/v1/uploads/create/',
                {
                    'filename': file.name,
                    'size': len(content),
                    'content_type': file.content_type,
                },
                format='json',
            )

            if response.status_code != 201:
                return response

            instruction = response.data['data']
            response = self.client.put(
                instruction['upload_url'],
                content,
                content_type=instruction['headers']['Content-Type'],
            )

            if response.status_code != 201:
                return response

            response = self.client.post(f'/api/v1/uploads/complete/{instruction["upload_id"]}/')

            if response.status_code != 202:
                return response

            GenericUploadWorkerService.run_once()
            self.uploads[key] = instruction['upload_id']

        return self.client.post(
            '/api/v1/submissions/create/',
            {
                'title': 'Proposal',
                'reviewer_id': str(self.reviewer.public_id),
                'client_request_id': self.request_id,
                'upload_id': self.uploads[key],
                **fields,
            },
            format='json',
        )

    def link(self, public_id, download=False):
        return self.client.get(
            f'/api/v1/submissions/file-link/{public_id}/?download={str(download).lower()}'
        )

    def test_upload_and_private_inline_view(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data['data']
        self.assertEqual(data['content'], '')
        self.assertEqual(data['file']['content_type'], 'application/pdf')
        self.assertNotIn('file_key', data)
        submission = Submission.objects.get()
        self.assertNotIn('proposal', submission.file_key)
        self.assertEqual(submission.file_size, len(PDF))
        link = self.link(data['id'])
        self.assertEqual(link.data['data']['expires_in'], 300)
        self.assertIn('no-store', link['Cache-Control'])
        content = self.client.get(link.data['data']['url'])
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content['Content-Type'], 'application/pdf')
        self.assertIn('inline', content['Content-Disposition'])
        self.assertEqual(content['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(b''.join(content.streaming_content), PDF)

    def test_download_uses_attachment_disposition(self):
        id = self.upload().data['data']['id']
        link = self.link(id, download=True)
        response = self.client.get(link.data['data']['url'])
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(b''.join(response.streaming_content), PDF)

    def test_link_and_content_require_current_assignment(self):
        id = self.upload().data['data']['id']
        owner_url = self.link(id).data['data']['url']
        self.client.force_login(self.other)
        self.assertEqual(self.link(id).status_code, 404)
        self.assertEqual(self.client.get(owner_url).status_code, 404)
        self.client.force_login(self.reviewer)
        reviewer_url = self.link(id).data['data']['url']
        self.reviewer.can_review = False
        self.reviewer.save()
        self.assertEqual(self.link(id).status_code, 404)
        self.assertEqual(self.client.get(reviewer_url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.link(id).status_code, 403)
        self.assertEqual(self.client.get(owner_url).status_code, 403)

    def test_signed_links_expire_and_cannot_be_changed(self):
        id = self.upload().data['data']['id']
        url = self.link(id).data['data']['url']
        self.assertEqual(self.client.get(url + 'broken').status_code, 403)

        with patch('django.core.signing.time.time', return_value=time.time() + FILE_LINK_TTL + 1):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_retry_keeps_one_file_and_changed_bytes_conflict(self):
        first = self.upload()
        second = self.upload()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['data']['id'], second.data['data']['id'])
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(len(list(Path(self.directory.name).rglob('*.pdf'))), 1)
        changed = self.upload(SimpleUploadedFile('proposal.pdf', PDF.replace(b'1.4', b'1.5')))
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(len(list(Path(self.directory.name).rglob('*.pdf'))), 2)

    def test_failed_event_write_keeps_validated_upload_for_retry(self):
        with patch(
            'nod_submission_service.services.generic_submission_service.SubmissionEvent.objects.create',
            side_effect=IntegrityError('failed event'),
        ):
            self.assertEqual(self.upload().status_code, 500)

        self.assertFalse(Submission.objects.exists())
        self.assertFalse(SubmissionEvent.objects.exists())
        self.assertEqual(DocumentUpload.objects.get().status, 'ready')
        self.assertEqual(len(list(Path(self.directory.name).rglob('*.pdf'))), 1)
        self.assertEqual(self.upload().status_code, 201)

    def test_storage_failure_does_not_create_submission(self):
        with patch.object(get_document_storage(), 'save', side_effect=OSError('unavailable')):
            self.assertEqual(self.upload().status_code, 500)

        self.assertFalse(Submission.objects.exists())

    def test_file_type_size_empty_and_conflicting_text_are_rejected(self):
        invalid = [
            SimpleUploadedFile('script.html', b'<html>hello</html>'),
            SimpleUploadedFile('fake.pdf', b'not a pdf'),
            SimpleUploadedFile('empty.txt', b''),
            SimpleUploadedFile('binary.txt', b'abc\x00def'),
            SimpleUploadedFile('large.txt', b'a' * (FILE_MAX_BYTES + 1)),
            SimpleUploadedFile('bad.docx', b'PK-not-a-zip'),
        ]

        for file in invalid:
            with self.subTest(name=file.name):
                self.assertIn(self.upload(file).status_code, (400, 409))

        self.assertEqual(self.upload(content='Also text').status_code, 400)
        self.assertFalse(Submission.objects.exists())

    def test_docx_rejects_macros_external_images_and_entities(self):
        invalid = [
            {'word/vbaProject.bin': b'macro'},
            {
                'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Type="image" Target="https://example.com/private"/></Relationships>'
            },
            {'word/test.xml': '<!DOCTYPE test [<!ENTITY x "value">]><test>&x;</test>'},
        ]

        for extra in invalid:
            self.assertEqual(self.upload(docx_file(extra)).status_code, 409)

    def test_docx_preview_is_cached_but_original_is_preserved(self):
        original = docx_file()
        original_bytes = original.read()
        original.seek(0)
        id = self.upload(original).data['data']['id']

        with patch(
            'nod_submission_service.services.generic_submission_service.convert_docx',
            return_value=ContentFile(PDF),
        ) as convert:
            first = self.link(id)
            self.assertEqual(first.status_code, 200, first.data)
            self.assertEqual(self.link(id).status_code, 200)
            convert.assert_called_once()

        preview = self.client.get(first.data['data']['url'])
        self.assertEqual(preview['Content-Type'], 'application/pdf')
        self.assertEqual(b''.join(preview.streaming_content), PDF)
        original = self.client.get(self.link(id, download=True).data['data']['url'])
        self.assertEqual(b''.join(original.streaming_content), original_bytes)

    def test_unavailable_converter_keeps_download_working(self):
        id = self.upload(docx_file()).data['data']['id']

        with patch(
            'nod_submission_service.services.generic_submission_service.convert_docx',
            side_effect=PreviewUnavailable(),
        ):
            self.assertEqual(self.link(id).status_code, 503)

        self.assertEqual(self.link(id, download=True).status_code, 200)
        self.assertEqual(Submission.objects.get().preview_key, '')

    @skipUnless(
        os.getenv('NOD_TEST_DOCX_PREVIEW') == 'true', 'Requires LibreOffice; enabled in CI.'
    )
    def test_real_docx_conversion(self):
        id = self.upload(docx_file()).data['data']['id']
        link = self.link(id)
        self.assertEqual(link.status_code, 200, link.data)
        response = self.client.get(link.data['data']['url'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))

    def test_text_is_served_as_plain_text_even_with_html_content(self):
        id = self.upload(SimpleUploadedFile('notes.txt', b'<script>alert(1)</script>')).data[
            'data'
        ]['id']
        response = self.client.get(self.link(id).data['data']['url'])
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(b''.join(response.streaming_content), b'<script>alert(1)</script>')

    def test_database_requires_text_or_file(self):
        self.upload()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.update(file_key='')

        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.update(content='Cannot include both')

    def test_cloud_signing_headers_and_permission_check(self):
        id = self.upload().data['data']['id']

        for provider, disposition in [
            ('azure', 'content_disposition'),
            ('s3', 'ResponseContentDisposition'),
        ]:
            with (
                override_settings(NOD_STORAGE_PROVIDER=provider),
                patch('utils.storage.factory.get_document_storage') as storage,
            ):
                storage.return_value.url.return_value = (
                    'https://private.example/document?signature=test'
                )
                result = self.link(id)
                self.assertEqual(result.status_code, 200)
                kwargs = storage.return_value.url.call_args.kwargs
                self.assertEqual(kwargs['expire'], 300)
                self.assertIn('inline', kwargs['parameters'][disposition])
                self.client.force_login(self.other)
                storage.return_value.url.reset_mock()
                self.assertEqual(self.link(id).status_code, 404)
                storage.return_value.url.assert_not_called()
                self.client.force_login(self.owner)
