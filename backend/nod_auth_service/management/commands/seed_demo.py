from django.core.management.base import BaseCommand, CommandError

from nod_submission_service.services.generic_demo_service import GenericDemoService


class Command(BaseCommand):
    help = 'Create local Nod demo accounts and example submissions.'

    def handle(self, *args, **options):
        try:
            users = GenericDemoService.seed()
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f'Demo ready: {len(users)} accounts. Password: NodDemo!2026')
        )
