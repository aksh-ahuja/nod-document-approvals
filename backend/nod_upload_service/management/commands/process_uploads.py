import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from nod_upload_service.constants import UPLOAD_CLEANUP_SECONDS, UPLOAD_POLL_SECONDS
from nod_upload_service.services.generic_upload_worker_service import GenericUploadWorkerService


class Command(BaseCommand):
    help = 'Validate queued document uploads and clean up expired files.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        next_cleanup = 0

        while True:
            close_old_connections()
            worked = GenericUploadWorkerService.run_once()

            if time.monotonic() >= next_cleanup:
                GenericUploadWorkerService.cleanup()
                next_cleanup = time.monotonic() + UPLOAD_CLEANUP_SECONDS

            if options['once']:
                return

            if not worked:
                time.sleep(UPLOAD_POLL_SECONDS)
