import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, close_old_connections
from django.test import TransactionTestCase

from unittest import skipUnless

from nod_auth_service.models import User
from nod_submission_service.models import Submission, SubmissionEvent
from nod_submission_service.services import GenericSubmissionService


@skipUnless(
    connection.vendor == 'postgresql', 'Row-lock tests require PostgreSQL; run make test-postgres.'
)
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            'owner@example.com', name='Owner', email_verified=True
        )
        self.reviewer = User.objects.create_user(
            'reviewer@example.com', name='Reviewer', can_review=True, email_verified=True
        )

    def test_competing_decisions_commit_exactly_once(self):
        submission = GenericSubmissionService.create_submission(
            self.owner, 'Concurrent review', 'Content', self.reviewer.public_id, uuid.uuid4()
        ).data
        barrier = Barrier(2)

        def decide(status):
            close_old_connections()

            try:
                reviewer = User.objects.get(pk=self.reviewer.pk)
                barrier.wait(timeout=10)

                return GenericSubmissionService.decide(
                    reviewer, submission.public_id, status, 'Decision note'
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(decide, ['approved', 'rejected']))

        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(
            SubmissionEvent.objects.filter(event_type__in=['approved', 'rejected']).count(), 1
        )

    def test_duplicate_creates_commit_once(self):
        key = uuid.uuid4()
        barrier = Barrier(2)

        def create(_):
            close_old_connections()

            try:
                owner = User.objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)

                return GenericSubmissionService.create_submission(
                    owner, 'Same document', 'Content', self.reviewer.public_id, key
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(create, range(2)))

        self.assertEqual(sorted(statuses), [200, 201])
        self.assertEqual(Submission.objects.count(), 1)

    def test_same_upload_cannot_be_attached_to_two_submissions(self):
        from datetime import timedelta
        from django.utils import timezone
        from nod_upload_service.models import DocumentUpload

        upload = DocumentUpload.objects.create(
            owner=self.owner,
            staging_key='staging/race',
            final_key='documents/race.txt',
            original_name='race.txt',
            expected_size=4,
            actual_size=4,
            content_type='text/plain',
            checksum='a' * 64,
            status='ready',
            upload_expires_at=timezone.now() + timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        barrier = Barrier(2)

        def create(_):
            close_old_connections()

            try:
                owner = User.objects.get(pk=self.owner.pk)
                barrier.wait(timeout=10)

                return GenericSubmissionService.create_submission(
                    owner,
                    'Same upload',
                    '',
                    self.reviewer.public_id,
                    uuid.uuid4(),
                    upload_id=upload.public_id,
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(create, range(2)))

        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(Submission.objects.count(), 1)

    def test_competing_workers_claim_a_job_once(self):
        from datetime import timedelta
        from django.utils import timezone
        from nod_upload_service.models import DocumentUpload
        from nod_upload_service.services.generic_upload_worker_service import (
            GenericUploadWorkerService,
        )

        DocumentUpload.objects.create(
            owner=self.owner,
            staging_key='staging/claim',
            original_name='notes.txt',
            expected_size=4,
            content_type='text/plain',
            status='validating',
            next_attempt_at=timezone.now(),
            upload_expires_at=timezone.now() + timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        barrier = Barrier(2)

        def claim(_):
            close_old_connections()

            try:
                barrier.wait(timeout=10)
                result = GenericUploadWorkerService.claim()

                return result.pk if result else None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = list(pool.map(claim, range(2)))

        self.assertEqual(sum(value is not None for value in claimed), 1)
