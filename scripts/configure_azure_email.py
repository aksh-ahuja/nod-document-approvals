#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
API_VERSION = '2023-03-31'
ARM = 'https://management.azure.com'


class SetupError(Exception):
    pass


def azure_json(*arguments):
    try:
        result = subprocess.run(
            ['az', *arguments, '--only-show-errors', '--output', 'json'],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise SetupError('Azure did not respond. Check your network and Azure login.') from exc

    if result.returncode:
        raise SetupError(
            'Azure CLI could not complete the request. Run az login and check your subscription, network, and resource permissions.'
        )

    return json.loads(result.stdout)


def resource_get(resource_id):
    return azure_json(
        'rest', '--method', 'get', '--url', f'{ARM}{resource_id}?api-version={API_VERSION}'
    )


def communication_services(subscription_id):
    # The generic ARM resource inventory can omit existing Communication Services.
    url = (
        f'{ARM}/subscriptions/{subscription_id}/providers/'
        f'Microsoft.Communication/communicationServices?api-version={API_VERSION}'
    )
    resources = []

    while url:
        page = azure_json('rest', '--method', 'get', '--url', url)
        resources.extend(page.get('value', []))
        url = page.get('nextLink')

    return resources


def sender_addresses(domain, usernames):
    properties = domain.get('properties', {})

    if properties.get('provisioningState') != 'Succeeded':
        return []

    if properties.get('domainManagement') != 'AzureManaged':
        states = properties.get('verificationStates', {})

        if any(
            states.get(key, {}).get('status') != 'Succeeded' for key in ['Domain', 'SPF', 'DKIM']
        ):
            return []

    sender_domain = properties.get('fromSenderDomain')

    if not sender_domain:
        return []

    return [
        f"{item['properties']['username']}@{sender_domain}"
        for item in usernames
        if item.get('properties', {}).get('username')
    ]


def find_senders(resources):
    choices = []

    for resource in resources:
        service = resource_get(resource['id'])
        properties = service.get('properties', {})

        if properties.get('provisioningState') != 'Succeeded':
            continue

        for domain_id in properties.get('linkedDomains', []):
            domain = resource_get(domain_id)
            url = f'{ARM}{domain_id}/senderUsernames?api-version={API_VERSION}'
            usernames = []

            while url:
                page = azure_json('rest', '--method', 'get', '--url', url)
                usernames.extend(page.get('value', []))
                url = page.get('nextLink')

            for sender in sender_addresses(domain, usernames):
                choices.append(
                    {
                        'resource_id': resource['id'],
                        'name': resource['name'],
                        'sender': sender,
                        'endpoint': f"https://{properties['hostName']}",
                    }
                )

    return choices


def choose_sender(choices, requested_sender):
    if requested_sender:
        choices = [
            choice for choice in choices if choice['sender'].lower() == requested_sender.lower()
        ]

    if not choices:
        raise SetupError(
            'No eligible linked sender found. Connect a verified Email Communication Services domain to a Communication Services resource first.'
        )

    for index, choice in enumerate(choices, 1):
        print(f"  {index}. {choice['name']} | {choice['sender']}")

    if len(choices) == 1:
        return choices[0]

    if not sys.stdin.isatty():
        raise SetupError('Multiple senders found. Pass --resource-id and --sender to select one.')

    selection = input('Sender number: ').strip()

    if not selection.isdigit() or not 1 <= int(selection) <= len(choices):
        raise SetupError('Invalid sender selection.')

    return choices[int(selection) - 1]


def write_env(path, values):
    source = path.read_text() if path.exists() else (ROOT / '.env.example').read_text()
    remaining = dict(values)
    lines = []

    for line in source.splitlines():
        key = line.split('=', 1)[0].strip().removeprefix('export ')

        if key in values:
            if key in remaining:
                lines.append(f'{key}={shlex.quote(remaining.pop(key))}')
        else:
            lines.append(line)

    lines.extend(f'{key}={shlex.quote(value)}' for key, value in remaining.items())
    fd, temporary = tempfile.mkstemp(prefix='.nod-email-', dir=path.parent)

    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')

        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_delivery(connection_string, sender, recipient):
    from azure.communication.email import EmailClient
    from azure.core.exceptions import AzureError

    message = {
        'senderAddress': sender,
        'recipients': {'to': [{'address': recipient}]},
        'content': {
            'subject': 'Nod email is connected',
            'plainText': 'Nod can now send email through Azure. Return to the registration screen and request a fresh verification code. This message is a delivery check, not an OTP.',
        },
    }

    try:
        with EmailClient.from_connection_string(connection_string) as client:
            result = client.begin_send(message, connection_timeout=5, read_timeout=10).result(
                timeout=30
            )
    except (AzureError, TimeoutError) as exc:
        raise SetupError(
            'Azure did not confirm the test email. Configuration was not changed.'
        ) from exc

    if not result or result.get('status') != 'Succeeded':
        raise SetupError('Azure did not accept the test email. Configuration was not changed.')

    print(f'Azure accepted the test message to {recipient}. Check your inbox and spam folder.')


def main():
    parser = argparse.ArgumentParser(description='Connect Nod to an existing Azure email sender.')
    parser.add_argument('--subscription')
    parser.add_argument('--resource-id')
    parser.add_argument('--sender')
    parser.add_argument(
        '--test-to',
        help='Send a clearly labelled connection-test email before saving configuration.',
    )
    args = parser.parse_args()

    if not shutil.which('az'):
        raise SetupError('Azure CLI is not installed.')

    account_args = ['account', 'show']

    if args.subscription:
        account_args.extend(['--subscription', args.subscription])

    account = azure_json(*account_args)
    print(f"Using subscription: {account['name']}")

    if args.resource_id:
        resources = [{'id': args.resource_id, 'name': args.resource_id.rsplit('/', 1)[-1]}]
    else:
        resources = communication_services(account['id'])

    selected = choose_sender(find_senders(resources), args.sender)
    keys = azure_json(
        'rest',
        '--method',
        'post',
        '--url',
        f"{ARM}{selected['resource_id']}/listKeys?api-version={API_VERSION}",
    )
    connection_string = keys.get('primaryConnectionString')

    if not connection_string and keys.get('primaryKey'):
        connection_string = f"endpoint={selected['endpoint']}/;accesskey={keys['primaryKey']}"

    if not connection_string:
        raise SetupError('Azure did not return an email connection string.')

    if args.test_to:
        check_delivery(connection_string, selected['sender'], args.test_to)

    write_env(
        ROOT / '.env',
        {
            'NOD_EMAIL_PROVIDER': 'azure',
            'NOD_EMAIL_SENDER': selected['sender'],
            'NOD_AZURE_EMAIL_ENDPOINT': selected['endpoint'],
            'NOD_AZURE_EMAIL_CONNECTION_STRING': connection_string,
        },
    )
    print(f"Nod is configured to send through {selected['sender']}.")
    print('Credentials were saved to .env with owner-only permissions.')
    print('Restart make api, then request a fresh code in the registration screen.')


if __name__ == '__main__':
    try:
        main()
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
