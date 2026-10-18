import hashlib
import logging
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from utils.storage.factory import get_document_storage
from utils.storage.uploads import UploadChanged, UploadMissing, get_upload_provider

from ..constants import (
    FILE_MAX_BYTES,
    UPLOAD_BATCH_SIZE,
    UPLOAD_LEASE_SECONDS,
    UPLOAD_MAX_ATTEMPTS,
    UPLOAD_RETRY_SECONDS,
)
from ..files import validate_document
from ..messages import FailureMessage
from ..models import DocumentUpload

logger = logging.getLogger(__name__)


class GenericUploadWorkerService:

    @classmethod
    @transaction.atomic
    def claim(cls):
        now = timezone.now()
        queue = DocumentUpload.objects.filter(
            status='validating', next_attempt_at__lte=now, expires_at__gt=now
        ).filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
        upload = (
            queue.select_for_update(
                skip_locked=connection.features.has_select_for_update_skip_locked
            )
            .order_by('next_attempt_at', 'id')
            .first()
        )

        if upload is None:
            return None

        if upload.attempts >= UPLOAD_MAX_ATTEMPTS:
            upload.status = 'rejected'
            upload.error = FailureMessage.UPLOAD_UNAVAILABLE
            upload.save(update_fields=['status', 'error', 'updated_at'])

            return None

        upload.attempts += 1
        upload.lease_token = uuid.uuid4()
        upload.lease_expires_at = now + timedelta(seconds=UPLOAD_LEASE_SECONDS)
        upload.save(update_fields=['attempts', 'lease_token', 'lease_expires_at', 'updated_at'])

        return upload

    @classmethod
    def run_once(cls):
        upload = cls.claim()

        if upload is None:
            return False

        try:
            cls.__validate(upload)
        except ValidationError as error:
            message = str(error.detail[0]) if isinstance(error.detail, list) else str(error.detail)
            cls.__owned_job(upload).update(status='rejected', error=message, lease_expires_at=None)
        except (UploadChanged, UploadMissing):
            cls.__owned_job(upload).update(
                status='rejected', error=FailureMessage.UPLOAD_CHANGED, lease_expires_at=None
            )
        except Exception:
            # A failed job must remain recoverable without taking down the worker.
            logger.exception('Upload validation failed for %s', upload.public_id)
            exhausted = upload.attempts >= UPLOAD_MAX_ATTEMPTS
            cls.__owned_job(upload).update(
                status='rejected' if exhausted else 'validating',
                error=FailureMessage.UPLOAD_UNAVAILABLE if exhausted else '',
                next_attempt_at=timezone.now()
                + timedelta(seconds=UPLOAD_RETRY_SECONDS * 2 ** (upload.attempts - 1)),
                lease_expires_at=None,
            )

        return True

    @classmethod
    def __owned_job(cls, upload):
        return DocumentUpload.objects.filter(
            pk=upload.pk, status='validating', lease_token=upload.lease_token
        )

    @classmethod
    def __validate(cls, upload):
        content = get_upload_provider().read(
            upload.staging_key, upload.storage_version, FILE_MAX_BYTES
        )

        if len(content) != upload.expected_size or len(content) > FILE_MAX_BYTES:
            raise ValidationError(FailureMessage.UPLOAD_SIZE_MISMATCH)

        file = ContentFile(content, name=upload.original_name)
        validate_document(file)
        checksum = hashlib.sha256(content).hexdigest()
        storage = get_document_storage()
        extension = Path(upload.original_name).suffix.lower()
        final_key = f'documents/{upload.public_id}/{upload.lease_token}{extension}'
        saved_key = ''

        try:
            saved_key = storage.save(final_key, file)
            published = (
                cls.__owned_job(upload)
                .filter(expires_at__gt=timezone.now())
                .update(
                    status='ready',
                    final_key=saved_key,
                    checksum=checksum,
                    content_type=file.content_type,
                    actual_size=len(content),
                    error='',
                    lease_expires_at=None,
                    updated_at=timezone.now(),
                )
            )
        except Exception:
            if saved_key:
                cls.__delete_file(storage, saved_key)

            raise

        if not published:
            cls.__delete_file(storage, saved_key)

    @classmethod
    def __delete_file(cls, storage, key):
        try:
            storage.delete(key)
        except Exception:
            logger.exception('Could not remove unused upload object %s', key)

    @classmethod
    def cleanup(cls):
        now = timezone.now()
        expired = DocumentUpload.objects.filter(
            expires_at__lte=now, cleaned_at__isnull=True
        ).filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
        ids = list(expired.order_by('expires_at').values_list('pk', flat=True)[:UPLOAD_BATCH_SIZE])
        storage = get_document_storage()

        for id in ids:
            with transaction.atomic():
                upload = DocumentUpload.objects.select_for_update().get(pk=id)

                if upload.cleaned_at or (
                    upload.lease_expires_at and upload.lease_expires_at > timezone.now()
                ):
                    continue

                try:
                    storage.delete(upload.staging_key)

                    prefix = f'documents/{upload.public_id}'

                    try:
                        _, files = storage.listdir(prefix)
                    except FileNotFoundError:
                        files = []

                    for filename in files:
                        key = f'{prefix}/{filename}'

                        if upload.status != 'attached' or key != upload.final_key:
                            storage.delete(key)
                except Exception:
                    logger.exception('Could not clean up upload %s', upload.public_id)
                    continue

                if upload.status != 'attached':
                    upload.status = 'expired'

                upload.cleaned_at = timezone.now()
                upload.save(update_fields=['status', 'cleaned_at', 'updated_at'])

        return len(ids)
