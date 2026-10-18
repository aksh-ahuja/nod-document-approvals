from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from utils.email.exceptions import EmailDeliveryError


class AzureEmailProvider:
    def send_otp(self, recipient, code):
        from azure.communication.email import EmailClient
        from azure.core.exceptions import AzureError
        from azure.identity import DefaultAzureCredential

        if not settings.NOD_EMAIL_SENDER:
            raise ImproperlyConfigured('Set NOD_EMAIL_SENDER to your verified Azure sender.')

        if settings.NOD_AZURE_EMAIL_CONNECTION_STRING:
            client = EmailClient.from_connection_string(settings.NOD_AZURE_EMAIL_CONNECTION_STRING)
        elif settings.NOD_AZURE_EMAIL_ENDPOINT:
            client = EmailClient(settings.NOD_AZURE_EMAIL_ENDPOINT, DefaultAzureCredential())
        else:
            raise ImproperlyConfigured('Configure an Azure Email endpoint or connection string.')

        message = {
            'senderAddress': settings.NOD_EMAIL_SENDER,
            'recipients': {'to': [{'address': recipient}]},
            'content': {
                'subject': 'Your Nod verification code',
                'plainText': (
                    f'Your Nod code is {code}. It expires in 10 minutes. '
                    'If you did not request this, ignore this email.'
                ),
                'html': (
                    '<div style="font-family:Arial,sans-serif;color:#18202b;'
                    'max-width:480px;padding:32px">'
                    '<h1>nod<span style="color:#3158ef">.</span></h1>'
                    '<h2>One last step.</h2><p>Use this code to verify your email.</p>'
                    f'<p style="font-size:36px;letter-spacing:8px;font-weight:bold">{code}</p>'
                    '<p>Expires in 10 minutes. Did not request this? '
                    'You can ignore this email.</p></div>'
                ),
            },
        }

        try:
            with client:
                result = client.begin_send(message, connection_timeout=5, read_timeout=10).result(
                    timeout=20
                )

            if not result or result.get('status') != 'Succeeded':
                raise EmailDeliveryError('Email delivery was not confirmed.')
        except (AzureError, TimeoutError) as exc:
            raise EmailDeliveryError('Azure email request failed.') from exc
