import sys
import types
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from utils.azure.email import AzureEmailProvider
from utils.email.exceptions import EmailDeliveryError
from utils.email.factory import get_email_provider, ConsoleEmailProvider


class AzureEmailTests(SimpleTestCase):
    def setUp(self):
        self.client_class = MagicMock()
        self.client = self.client_class.from_connection_string.return_value
        self.client.__enter__.return_value = self.client
        self.client.begin_send.return_value.result.return_value = {'status': 'Succeeded'}
        self.azure_error = type('AzureError', (Exception,), {})
        modules = {}

        for name in [
            'azure',
            'azure.communication',
            'azure.communication.email',
            'azure.core',
            'azure.core.exceptions',
            'azure.identity',
        ]:
            modules[name] = types.ModuleType(name)

        modules['azure.communication.email'].EmailClient = self.client_class
        modules['azure.core.exceptions'].AzureError = self.azure_error
        modules['azure.identity'].DefaultAzureCredential = MagicMock()
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    @override_settings(
        NOD_EMAIL_SENDER='verified@example.com', NOD_AZURE_EMAIL_CONNECTION_STRING='test-connection'
    )
    def test_azure_message_has_sender_recipient_and_code(self):
        AzureEmailProvider().send_otp('user@example.com', '123456')
        message = self.client.begin_send.call_args.args[0]
        self.assertEqual(message['senderAddress'], 'verified@example.com')
        self.assertEqual(message['recipients']['to'][0]['address'], 'user@example.com')
        self.assertIn('123456', message['content']['plainText'])
        self.assertIn('123456', message['content']['html'])
        self.client.begin_send.return_value.result.assert_called_once_with(timeout=20)

    @override_settings(
        NOD_EMAIL_SENDER='verified@example.com', NOD_AZURE_EMAIL_CONNECTION_STRING='test-connection'
    )
    def test_provider_failure_is_specific_delivery_error(self):
        self.client.begin_send.side_effect = self.azure_error('Unavailable')

        with self.assertRaises(EmailDeliveryError):
            AzureEmailProvider().send_otp('user@example.com', '123456')

    @override_settings(DEBUG=True, NOD_EMAIL_PROVIDER='console')
    def test_local_factory_selection(self):
        self.assertIsInstance(get_email_provider(), ConsoleEmailProvider)
