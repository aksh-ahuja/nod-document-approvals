from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from nod_auth_service.constants import LOGIN_HOURLY_LIMIT
from utils.proxy import TrustedProxyMiddleware


@override_settings(NOD_TRUSTED_PROXY_IPS={'172.29.80.1'})
class TrustedProxyTests(SimpleTestCase):
    def request(self, peer, real_ip='203.0.113.8', scheme='https'):
        request = RequestFactory().get(
            '/', REMOTE_ADDR=peer, HTTP_X_REAL_IP=real_ip, HTTP_X_FORWARDED_PROTO=scheme
        )
        TrustedProxyMiddleware(lambda request: HttpResponse())(request)
        return request

    def test_trusted_edge_sets_secure_scheme_and_client_rate_limit_address(self):
        request = self.request('172.29.80.1')
        self.assertTrue(request.is_secure())
        self.assertEqual(request.META['REMOTE_ADDR'], '203.0.113.8')

    def test_untrusted_peer_cannot_spoof_scheme_or_client_address(self):
        request = self.request('198.51.100.9')
        self.assertFalse(request.is_secure())
        self.assertEqual(request.META['REMOTE_ADDR'], '198.51.100.9')

    def test_malformed_forwarded_values_are_not_used(self):
        request = self.request('172.29.80.1', real_ip='203.0.113.8, 127.0.0.1', scheme='https,http')
        self.assertFalse(request.is_secure())
        self.assertEqual(request.META['REMOTE_ADDR'], '172.29.80.1')

    def test_ipv6_client_address_is_preserved(self):
        request = self.request('172.29.80.1', real_ip='2001:db8::8')
        self.assertEqual(request.META['REMOTE_ADDR'], '2001:db8::8')


@override_settings(NOD_TRUSTED_PROXY_IPS={'127.0.0.1', '172.29.80.10'})
class ProxyRateLimitTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        authentication = patch(
            'nod_auth_service.services.generic_auth_service.authenticate', return_value=None
        )
        authentication.start()
        self.addCleanup(authentication.stop)

    def login(self, peer, client_ip, email):
        return self.client.post(
            '/api/v1/auth/login/',
            {'email': email, 'password': 'Example-password-2026'},
            format='json',
            REMOTE_ADDR=peer,
            HTTP_X_REAL_IP=client_ip,
            HTTP_X_FORWARDED_FOR=f'198.51.100.99, {client_ip}',
            HTTP_X_FORWARDED_PROTO='https',
        )

    def test_one_clients_limit_does_not_block_other_clients_or_replicas(self):
        for _ in range(LOGIN_HOURLY_LIMIT):
            response = self.login('127.0.0.1', '203.0.113.8', 'first@example.com')
            self.assertEqual(response.status_code, 401)

        blocked = self.login('172.29.80.10', '203.0.113.8', 'another@example.com')
        independent = self.login('127.0.0.1', '203.0.113.9', 'second@example.com')
        compose_client = self.login('172.29.80.10', '2001:db8::9', 'third@example.com')

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(independent.status_code, 401)
        self.assertEqual(compose_client.status_code, 401)

    def test_untrusted_client_cannot_evade_limits_with_forwarded_headers(self):
        for attempt in range(LOGIN_HOURLY_LIMIT):
            response = self.login(
                '198.51.100.8', f'203.0.113.{attempt + 1}', f'person{attempt}@example.com'
            )
            self.assertEqual(response.status_code, 401)

        response = self.login('198.51.100.8', '203.0.113.200', 'different@example.com')
        self.assertEqual(response.status_code, 429)
