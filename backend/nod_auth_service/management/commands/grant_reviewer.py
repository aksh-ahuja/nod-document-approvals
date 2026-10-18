from django.core.management.base import BaseCommand, CommandError

from nod_auth_service.services import GenericAuthService


class Command(BaseCommand):
    help = 'Grant reviewer access to an active, verified Nod user.'

    def add_arguments(self, parser):
        parser.add_argument('email')

    def handle(self, *args, **options):
        if not GenericAuthService.grant_reviewer(options['email']):
            raise CommandError('No active verified user with that email.')

        self.stdout.write(self.style.SUCCESS('Reviewer access granted.'))
