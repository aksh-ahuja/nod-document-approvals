import importlib.util
import os
from pathlib import Path
import shlex
import stat
import tempfile
from unittest import TestCase
from unittest.mock import patch

script = Path(__file__).resolve().parents[2] / 'scripts' / 'configure_azure_email.py'
spec = importlib.util.spec_from_file_location('nod_azure_setup', script)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class AzureSetupTests(TestCase):
    def test_service_discovery_uses_provider_api_and_follows_pagination(self):
        next_page = f'{setup.ARM}/next-page'
        with patch.object(
            setup,
            'azure_json',
            side_effect=[
                {'value': [{'id': 'first'}], 'nextLink': next_page},
                {'value': [{'id': 'second'}]},
            ],
        ) as request:
            self.assertEqual(
                setup.communication_services('subscription'),
                [
                    {'id': 'first'},
                    {'id': 'second'},
                ],
            )
        self.assertIn(
            '/Microsoft.Communication/communicationServices?', request.call_args_list[0].args[-1]
        )
        self.assertEqual(request.call_args_list[1].args[-1], next_page)

    def test_env_update_preserves_settings_and_quotes_connection_string(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text(
                'NOD_DEBUG=true\nNOD_EMAIL_PROVIDER=console\nNOD_EMAIL_SENDER=old@example.com\n'
            )
            secret = 'endpoint=https://example.test/;accesskey=a+b/c=='
            setup.write_env(
                path, {'NOD_EMAIL_PROVIDER': 'azure', 'NOD_AZURE_EMAIL_CONNECTION_STRING': secret}
            )
            content = path.read_text()
            self.assertIn('NOD_DEBUG=true', content)
            self.assertIn('NOD_EMAIL_SENDER=old@example.com', content)
            self.assertEqual(content.count('NOD_EMAIL_PROVIDER='), 1)
            values = dict(token.split('=', 1) for token in shlex.split(content))
            self.assertEqual(values['NOD_AZURE_EMAIL_CONNECTION_STRING'], secret)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_atomic_write_failure_keeps_original_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('NOD_EMAIL_PROVIDER=console\n')

            with patch.object(setup.os, 'replace', side_effect=OSError('Disk unavailable')):
                with self.assertRaises(OSError):
                    setup.write_env(path, {'NOD_EMAIL_PROVIDER': 'azure'})

            self.assertEqual(path.read_text(), 'NOD_EMAIL_PROVIDER=console\n')
            self.assertEqual(os.listdir(directory), ['.env'])

    def test_custom_domain_must_be_verified(self):
        domain = {
            'properties': {
                'provisioningState': 'Succeeded',
                'domainManagement': 'CustomerManaged',
                'fromSenderDomain': 'example.com',
            }
        }
        users = [{'properties': {'username': 'hello'}}]
        self.assertEqual(setup.sender_addresses(domain, users), [])
        domain['properties']['verificationStates'] = {
            key: {'status': 'Succeeded'} for key in ['Domain', 'SPF', 'DKIM']
        }
        self.assertEqual(setup.sender_addresses(domain, users), ['hello@example.com'])

    def test_sender_uses_visible_domain_not_return_path(self):
        domain = {
            'properties': {
                'provisioningState': 'Succeeded',
                'domainManagement': 'AzureManaged',
                'fromSenderDomain': 'example.azurecomm.net',
                'mailFromSenderDomain': 'bounce.example.azurecomm.net',
            }
        }
        self.assertEqual(
            setup.sender_addresses(domain, [{'properties': {'username': 'DoNotReply'}}]),
            ['DoNotReply@example.azurecomm.net'],
        )

    def test_multiple_resources_require_explicit_selection(self):
        choices = [
            {'name': 'one', 'sender': 'a@example.com'},
            {'name': 'two', 'sender': 'b@example.com'},
        ]

        with patch.object(setup.sys.stdin, 'isatty', return_value=False), patch('builtins.print'):
            with self.assertRaises(setup.SetupError):
                setup.choose_sender(choices, None)

            self.assertEqual(setup.choose_sender(choices, 'b@example.com')['name'], 'two')

    def test_cli_error_does_not_print_potential_secret_output(self):
        with patch.object(setup.subprocess, 'run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = 'secret-connection-string'

            with self.assertRaises(setup.SetupError) as error:
                setup.azure_json('account', 'show')

            self.assertNotIn('secret-connection-string', str(error.exception))
