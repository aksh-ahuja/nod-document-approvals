import uuid
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from nod_auth_service.models import User
from nod_submission_service.models import Submission, SubmissionEvent
from nod_submission_service.services import GenericSubmissionService


class SubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('owner@example.com', name='Owner', email_verified=True)
        cls.reviewer = User.objects.create_user(
            'reviewer@example.com', name='Reviewer', can_review=True, email_verified=True
        )
        cls.other = User.objects.create_user(
            'other@example.com', name='Other reviewer', can_review=True, email_verified=True
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.payload = {
            'title': 'Launch plan',
            'content': 'Please review this plan.',
            'reviewer_id': str(self.reviewer.public_id),
            'client_request_id': str(uuid.uuid4()),
        }

    def create(self):
        response = self.client.post('/api/v1/submissions/create/', self.payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.public_id = response.data['data']['id']

        return response

    def decide(self, decision='approved', note=''):
        return self.client.post(
            f'/api/v1/submissions/decision/{self.public_id}/',
            {'decision': decision, 'note': note},
            format='json',
        )

    def test_create_sets_owner_pending_status_and_history(self):
        self.payload.update(status='approved', submitter_id=str(self.other.public_id))
        response = self.create()
        self.assertEqual(response.data['data']['status'], 'pending')
        self.assertEqual(response.data['data']['submitter']['id'], str(self.owner.public_id))
        self.assertEqual(SubmissionEvent.objects.get().event_type, 'submitted')

    def test_duplicate_request_replays_and_changed_payload_conflicts(self):
        first = self.create()
        second = self.client.post('/api/v1/submissions/create/', self.payload, format='json')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['data']['id'], second.data['data']['id'])
        self.assertEqual(Submission.objects.count(), 1)
        self.payload['content'] = 'Changed content'
        self.assertEqual(
            self.client.post(
                '/api/v1/submissions/create/', self.payload, format='json'
            ).status_code,
            409,
        )

    def test_self_review_nonreviewer_and_inactive_reviewer_rejected(self):
        restricted = User.objects.create_user(
            'restricted@example.com', name='Restricted', email_verified=True, can_review=False
        )

        for reviewer in [self.owner, restricted, self.other]:
            if reviewer == self.other:
                reviewer.is_active = False
                reviewer.save()

            self.payload['reviewer_id'] = str(reviewer.public_id)
            self.assertEqual(
                self.client.post(
                    '/api/v1/submissions/create/', self.payload, format='json'
                ).status_code,
                400,
            )

        self.assertFalse(Submission.objects.exists())

    def test_verified_user_can_submit_and_review_assigned_documents_by_default(self):
        self.assertTrue(self.owner.can_review)
        self.create()
        self.client.force_login(self.reviewer)
        self.payload['reviewer_id'] = str(self.owner.public_id)
        self.payload['client_request_id'] = str(uuid.uuid4())
        self.create()

        self.client.force_login(self.owner)
        assigned = self.client.get('/api/v1/submissions/list/?scope=assigned')
        own = self.client.get('/api/v1/submissions/list/?scope=mine')

        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.data['data']['count'], 1)
        self.assertEqual(assigned.data['data']['results'][0]['id'], self.public_id)
        self.assertEqual(own.data['data']['count'], 1)
        self.assertEqual(self.decide().status_code, 200)

    def test_empty_content_and_missing_reviewer_fail(self):
        self.payload['content'] = '  '
        response = self.client.post('/api/v1/submissions/create/', self.payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('content', response.data['errors'])
        self.payload['content'] = 'Content'
        del self.payload['reviewer_id']
        self.assertEqual(
            self.client.post(
                '/api/v1/submissions/create/', self.payload, format='json'
            ).status_code,
            400,
        )

    def test_only_owner_and_assigned_reviewer_can_read(self):
        self.create()
        self.client.force_login(self.other)

        for path in ['detail', 'history']:
            self.assertEqual(
                self.client.get(f'/api/v1/submissions/{path}/{self.public_id}/').status_code, 404
            )

        self.assertEqual(
            self.client.get('/api/v1/submissions/list/?scope=assigned').data['data']['count'], 0
        )
        self.assertEqual(self.decide().status_code, 404)
        self.client.force_login(self.reviewer)
        self.assertEqual(
            self.client.get(f'/api/v1/submissions/detail/{self.public_id}/').status_code, 200
        )

    def test_owner_cannot_decide_even_with_review_permission(self):
        self.create()
        self.owner.can_review = True
        self.owner.save()
        self.assertEqual(self.decide().status_code, 403)

    def test_decision_is_terminal_and_identical_retry_is_safe(self):
        self.create()
        self.client.force_login(self.reviewer)
        self.assertEqual(self.decide('approved', 'Ready.').status_code, 200)
        self.assertEqual(self.decide('approved', 'Ready.').status_code, 200)
        self.assertEqual(self.decide('rejected', 'Changed my mind.').status_code, 409)
        self.assertEqual(SubmissionEvent.objects.count(), 2)
        self.assertIsNotNone(Submission.objects.get().decided_at)

    def test_rejection_requires_reason_and_history_exposes_it(self):
        self.create()
        self.client.force_login(self.reviewer)
        self.assertEqual(self.decide('rejected', '  ').status_code, 400)
        self.assertEqual(self.decide('rejected', 'Add the budget.').status_code, 200)
        self.client.force_login(self.owner)
        history = self.client.get(f'/api/v1/submissions/history/{self.public_id}/').data['data']
        self.assertEqual(history[-1]['note'], 'Add the budget.')
        self.assertEqual(history[-1]['actor']['id'], str(self.reviewer.public_id))

    def test_event_failure_rolls_back_decision(self):
        self.create()

        with patch(
            'nod_submission_service.services.generic_submission_service.SubmissionEvent.objects.create',
            side_effect=RuntimeError('write failed'),
        ):
            with self.assertRaises(RuntimeError):
                GenericSubmissionService.decide(self.reviewer, self.public_id, 'approved', '')

        self.assertEqual(Submission.objects.get().status, 'pending')
        self.assertEqual(SubmissionEvent.objects.count(), 1)

    def test_database_rejects_inconsistent_terminal_status(self):
        self.create()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.update(status='approved')

    def test_filter_summary_pagination_and_no_mutation_endpoints(self):
        self.create()
        self.assertEqual(
            self.client.get('/api/v1/submissions/list/?status=pending').data['data']['count'], 1
        )
        self.assertEqual(
            self.client.get('/api/v1/submissions/list/?status=approved').data['data']['count'], 0
        )
        self.assertEqual(
            self.client.get('/api/v1/submissions/list/?status=invalid').status_code, 400
        )
        self.assertEqual(self.client.get('/api/v1/submissions/list/?page=999').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/submissions/summary/').data['data']['pending'], 1)
        self.assertEqual(
            self.client.patch(
                f'/api/v1/submissions/detail/{self.public_id}/', {'content': 'Changed'}
            ).status_code,
            405,
        )

    def test_anonymous_access_denied(self):
        self.client.logout()
        self.assertEqual(
            self.client.post(
                '/api/v1/submissions/create/', self.payload, format='json'
            ).status_code,
            403,
        )
