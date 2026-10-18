import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from nod_auth_service.models import User, RegistrationChallenge
from nod_auth_service.services import GenericAuthService
from utils.email.exceptions import EmailDeliveryError


@override_settings(NOD_EMAIL_PROVIDER='console', DEBUG=True)
class RegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.delivery = patch('nod_auth_service.services.generic_auth_service.get_email_provider')
        self.provider = self.delivery.start().return_value
        self.addCleanup(self.delivery.stop)
        self.payload = {
            'name': 'Taylor Smith',
            'email': 'Taylor@example.com',
            'password': 'A-strong-password-2026',
        }

    def register(self):
        response = self.client.post('/api/v1/auth/register/', self.payload, format='json')
        self.assertEqual(response.status_code, 202, response.data)
        self.code = self.provider.send_otp.call_args.args[1]
        self.challenge_id = response.data['data']['challenge_id']

        return response

    def verify(self, code=None):
        return self.client.post(
            '/api/v1/auth/verify/',
            {'challenge_id': self.challenge_id, 'code': code or self.code},
            format='json',
        )

    def test_registration_requires_verification_and_enables_submission_and_review(self):
        response = self.register()
        self.assertFalse(User.objects.exists())
        self.assertNotIn(self.code, str(response.data))
        challenge = RegistrationChallenge.objects.get()
        self.assertNotEqual(challenge.code_hash, self.code)
        self.assertNotEqual(challenge.password_hash, self.payload['password'])
        verified = self.verify()
        self.assertEqual(verified.status_code, 201)
        user = User.objects.get()
        self.assertEqual(user.email, 'taylor@example.com')
        self.assertTrue(user.email_verified)
        self.assertTrue(user.can_review)
        self.assertTrue(user.check_password(self.payload['password']))
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 200)
        challenge.refresh_from_db()
        self.assertEqual(challenge.password_hash, '')
        self.assertIsNotNone(challenge.consumed_at)

    def test_code_cannot_be_reused(self):
        self.register()
        self.assertEqual(self.verify().status_code, 201)
        self.assertEqual(self.verify().status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_expired_code_is_rejected(self):
        self.register()
        RegistrationChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify().status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_attempt_limit_survives_wrong_guesses(self):
        self.register()
        wrong = '000000' if self.code != '000000' else '000001'

        for _ in range(5):
            self.assertEqual(self.verify(wrong).status_code, 400)

        self.assertEqual(self.verify().status_code, 429)
        self.assertFalse(User.objects.exists())

    def test_resend_has_cooldown_and_invalidates_old_challenge(self):
        self.register()
        old_id = self.challenge_id
        response = self.client.post('/api/v1/auth/resend/', {'challenge_id': old_id}, format='json')
        self.assertEqual(response.status_code, 429)
        RegistrationChallenge.objects.update(sent_at=timezone.now() - timedelta(seconds=61))
        response = self.client.post('/api/v1/auth/resend/', {'challenge_id': old_id}, format='json')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.verify().status_code, 400)
        self.challenge_id = response.data['data']['challenge_id']
        self.code = self.provider.send_otp.call_args.args[1]
        self.assertEqual(self.verify().status_code, 201)

    def test_delivery_failure_never_activates_account(self):
        self.provider.send_otp.side_effect = EmailDeliveryError('Temporary outage')
        response = self.client.post('/api/v1/auth/register/', self.payload, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(User.objects.exists())
        self.assertLessEqual(RegistrationChallenge.objects.get().expires_at, timezone.now())

    def test_weak_password_is_field_error(self):
        response = self.client.post(
            '/api/v1/auth/register/', {**self.payload, 'password': '123456'}, format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data['errors'])

    def test_client_cannot_control_account_permissions(self):
        self.payload['can_review'] = False
        self.payload['is_superuser'] = True
        self.payload['is_staff'] = True
        self.register()
        self.verify()
        user = User.objects.get()
        self.assertTrue(user.can_review)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_email_rate_limit(self):
        for index in range(5):
            self.assertTrue(GenericAuthService.take_rate_slot('email:test', 5))

        self.assertFalse(GenericAuthService.take_rate_slot('email:test', 5))

    def test_invalid_challenge_is_handled(self):
        response = self.client.post(
            '/api/v1/auth/verify/',
            {'challenge_id': str(uuid.uuid4()), 'code': '123456'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)


class AuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'jamie@example.com', 'Secret-password-2026', name='Jamie', email_verified=True
        )
        self.client = APIClient()

    def test_login_logout_and_session_revocation(self):
        response = self.client.post(
            '/api/v1/auth/login/',
            {'email': 'JAMIE@example.com', 'password': 'Secret-password-2026'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        session_cookie = self.client.cookies['nod_session'].value
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/logout/').status_code, 200)
        self.client.cookies['nod_session'] = session_cookie
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 403)

    def test_csrf_required_even_before_login(self):
        client = APIClient(enforce_csrf_checks=True)
        data = {'email': self.user.email, 'password': 'Secret-password-2026'}
        self.assertEqual(client.post('/api/v1/auth/login/', data, format='json').status_code, 403)
        bootstrap = client.get('/api/v1/auth/bootstrap/').json()['data']
        response = client.post(
            '/api/v1/auth/login/', data, format='json', HTTP_X_CSRFTOKEN=bootstrap['csrf_token']
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post('/api/v1/auth/logout/').status_code, 403)
        self.assertEqual(
            client.post(
                '/api/v1/auth/logout/', HTTP_X_CSRFTOKEN=response.data['data']['csrf_token']
            ).status_code,
            200,
        )

    def test_inactive_or_unverified_users_cannot_login(self):
        for field in ['is_active', 'email_verified']:
            setattr(self.user, field, False)
            self.user.save()
            response = self.client.post(
                '/api/v1/auth/login/',
                {'email': self.user.email, 'password': 'Secret-password-2026'},
                format='json',
            )
            self.assertEqual(response.status_code, 401)
            setattr(self.user, field, True)

    def test_reviewers_list_excludes_self_and_ineligible_accounts(self):
        self.user.can_review = True
        self.user.save()
        reviewer = User.objects.create_user(
            'alex@example.com', name='Alex', can_review=True, email_verified=True
        )
        User.objects.create_user(
            'sam@example.com', name='Sam', can_review=True, email_verified=True, is_active=False
        )
        self.client.force_login(self.user)
        response = self.client.get('/api/v1/reviewers/list/')
        self.assertEqual([u['id'] for u in response.data['data']], [str(reviewer.public_id)])
