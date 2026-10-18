import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class ConsoleEmailProvider:
    def send_otp(self, recipient, code):
        logger.info('Nod local email | To: %s | Verification code: %s', recipient, code)


def get_email_provider():
    if settings.NOD_EMAIL_PROVIDER == 'console' and settings.DEBUG:
        return ConsoleEmailProvider()

    if settings.NOD_EMAIL_PROVIDER == 'azure':
        from utils.azure.email import AzureEmailProvider

        return AzureEmailProvider()

    raise ImproperlyConfigured(
        'Choose azure, or console in local development, for NOD_EMAIL_PROVIDER.'
    )
