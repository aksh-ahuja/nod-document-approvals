from django.core.management.base import BaseCommand

from nod_auth_service.services import GenericAuthService


class Command(BaseCommand):
    help = 'Delete authentication challenges and rate windows expired for more than a day.'

    def handle(self, *args, **options):
        challenges, limits = GenericAuthService.cleanup_expired_auth()
        self.stdout.write(f'Removed {challenges} expired challenges and {limits} rate windows.')
