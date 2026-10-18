import uuid
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class UploadAppMigrationTests(TransactionTestCase):
    old_targets = [
        ('nod_submission_service', '0003_documentupload'),
        ('nod_upload_service', None),
    ]
    new_targets = [
        ('nod_submission_service', '0004_move_document_upload'),
        ('nod_upload_service', '0001_move_document_upload'),
    ]

    def migrate_to(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        state_targets = [target for target in targets if target[1] is not None]

        return executor.loader.project_state(state_targets).apps

    def test_move_preserves_records_relations_and_permission_identity(self):
        try:
            apps = self.migrate_to(self.old_targets)
            User = apps.get_model('nod_auth_service', 'User')
            Submission = apps.get_model('nod_submission_service', 'Submission')
            Upload = apps.get_model('nod_submission_service', 'DocumentUpload')
            ContentType = apps.get_model('contenttypes', 'ContentType')
            Permission = apps.get_model('auth', 'Permission')
            owner = User.objects.create(email='migration-owner@example.com', name='Owner')
            reviewer = User.objects.create(email='migration-reviewer@example.com', name='Reviewer')
            submission = Submission.objects.create(
                submitter_id=owner.pk,
                assigned_reviewer_id=reviewer.pk,
                title='Existing document',
                content='',
                file_key='documents/existing.txt',
                file_name='existing.txt',
                file_size=6,
                file_content_type='text/plain',
                client_request_id=uuid.uuid4(),
                request_hash='a' * 64,
            )
            upload = Upload.objects.create(
                owner_id=owner.pk,
                submission_id=submission.pk,
                status='attached',
                staging_key='staging/existing',
                final_key=submission.file_key,
                original_name=submission.file_name,
                expected_size=6,
                actual_size=6,
                content_type='text/plain',
                checksum='b' * 64,
                upload_expires_at=timezone.now() + timedelta(minutes=5),
                expires_at=timezone.now() + timedelta(days=1),
            )
            content_type, _ = ContentType.objects.get_or_create(
                app_label='nod_submission_service', model='documentupload'
            )
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type,
                codename='view_documentupload',
                defaults={'name': 'Can view document upload'},
            )

            apps = self.migrate_to(self.new_targets)
            moved = apps.get_model('nod_upload_service', 'DocumentUpload').objects.get(pk=upload.pk)
            self.assertEqual(moved.public_id, upload.public_id)
            self.assertEqual(moved.owner_id, owner.pk)
            self.assertEqual(moved.submission_id, submission.pk)
            self.assertEqual(moved.status, 'attached')
            self.assertEqual(moved.final_key, submission.file_key)
            self.assertEqual(moved.checksum, upload.checksum)
            self.assertEqual(moved.submission.upload.pk, upload.pk)
            content_type.refresh_from_db()
            self.assertEqual(content_type.app_label, 'nod_upload_service')
            permission.refresh_from_db()
            self.assertEqual(permission.content_type_id, content_type.pk)

            apps = self.migrate_to(self.old_targets)
            restored = apps.get_model('nod_submission_service', 'DocumentUpload').objects.get(
                pk=upload.pk
            )
            self.assertEqual(restored.public_id, upload.public_id)
            self.assertEqual(restored.submission_id, submission.pk)
            content_type.refresh_from_db()
            self.assertEqual(content_type.app_label, 'nod_submission_service')
        finally:
            self.migrate_to(self.new_targets)
