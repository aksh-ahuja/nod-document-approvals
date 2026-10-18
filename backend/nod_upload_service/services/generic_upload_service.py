import logging
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nod_auth_service.services import GenericAuthService
from utils.dto import GenericFuncResp
from utils.storage.constants import FILE_TYPES
from utils.storage.factory import get_document_storage
from utils.storage.uploads import StorageUnavailable, UploadMissing, get_upload_provider

from ..constants import (
    UPLOAD_ACTIVE_LIMIT,
    UPLOAD_HOURLY_LIMIT,
    UPLOAD_RETENTION_SECONDS,
    UPLOAD_TOKEN_SALT,
    UPLOAD_URL_TTL,
)
from ..messages import FailureMessage
from ..models import DocumentUpload

logger = logging.getLogger(__name__)


class GenericUploadService:

    @classmethod
    def get_uploads(cls, owner=None, public_id=None):
        uploads = DocumentUpload.objects.all()

        if owner is not None:
            uploads = uploads.filter(owner=owner)

        if public_id is not None:
            uploads = uploads.filter(public_id=public_id)

        return uploads

    @classmethod
    def get_ready_upload(cls, user, public_id):
        upload = cls.get_uploads(owner=user, public_id=public_id).select_for_update().first()

        if upload is None:
            return GenericFuncResp(False, FailureMessage.UPLOAD_NOT_FOUND, status_code=404)

        if upload.status == 'attached':
            return GenericFuncResp(False, FailureMessage.UPLOAD_USED, status_code=409)

        if upload.expires_at <= timezone.now():
            return GenericFuncResp(False, FailureMessage.UPLOAD_EXPIRED, status_code=410)

        if upload.status != 'ready':
            return GenericFuncResp(
                False, upload.error or FailureMessage.UPLOAD_NOT_READY, status_code=409
            )

        return GenericFuncResp(True, data=upload)

    @classmethod
    def attach_to_submission(cls, upload, submission_id):
        upload.status = 'attached'
        upload.submission_id = submission_id
        upload.save(update_fields=['status', 'submission', 'updated_at'])

    @classmethod
    def create(cls, user, filename, size):
        if not GenericAuthService.take_rate_slot(f'upload:{user.pk}', UPLOAD_HOURLY_LIMIT):
            return GenericFuncResp(False, FailureMessage.UPLOAD_LIMIT, status_code=429)

        with transaction.atomic():
            GenericAuthService.get_users(public_id=user.public_id).select_for_update().get()
            now = timezone.now()
            active = (
                cls.get_uploads(owner=user)
                .filter(
                    Q(status='pending', upload_expires_at__gt=now)
                    | Q(status__in=['validating', 'ready']),
                    expires_at__gt=now,
                )
                .count()
            )

            if active >= UPLOAD_ACTIVE_LIMIT:
                return GenericFuncResp(False, FailureMessage.UPLOAD_LIMIT, status_code=429)

            upload = DocumentUpload.objects.create(
                owner=user,
                staging_key=f'staging/{uuid.uuid4().hex}',
                original_name=filename,
                expected_size=size,
                content_type=FILE_TYPES[Path(filename).suffix.lower()],
                upload_expires_at=now + timedelta(seconds=UPLOAD_URL_TTL),
                expires_at=now + timedelta(seconds=UPLOAD_RETENTION_SECONDS),
            )

        try:
            instruction = get_upload_provider().sign(upload, UPLOAD_URL_TTL)
        except StorageUnavailable:
            cls.get_uploads(public_id=upload.public_id).update(status='rejected')
            logger.exception('Could not sign upload %s', upload.public_id)

            return GenericFuncResp(False, FailureMessage.UPLOAD_UNAVAILABLE, status_code=503)

        return GenericFuncResp(
            True,
            data={
                'upload_id': str(upload.public_id),
                'expires_in': UPLOAD_URL_TTL,
                **instruction,
            },
            status_code=201,
        )

    @classmethod
    def status(cls, user, public_id):
        upload = cls.get_uploads(owner=user, public_id=public_id).first()

        if upload is None:
            return GenericFuncResp(False, FailureMessage.UPLOAD_NOT_FOUND, status_code=404)

        status = upload.status
        error = upload.error

        if status != 'attached' and upload.expires_at <= timezone.now():
            status, error = 'expired', FailureMessage.UPLOAD_EXPIRED
        elif status == 'pending' and upload.upload_expires_at <= timezone.now():
            status, error = 'expired', FailureMessage.UPLOAD_EXPIRED

        return GenericFuncResp(
            True,
            data={
                'upload_id': str(upload.public_id),
                'status': status,
                'error': error,
                'name': upload.original_name,
            },
        )

    @classmethod
    def complete(cls, user, public_id):
        upload = cls.get_uploads(owner=user, public_id=public_id).first()

        if upload is None:
            return GenericFuncResp(False, FailureMessage.UPLOAD_NOT_FOUND, status_code=404)

        if upload.status != 'pending':
            return cls.status(user, public_id)

        if upload.upload_expires_at <= timezone.now():
            return GenericFuncResp(False, FailureMessage.UPLOAD_EXPIRED, status_code=410)

        try:
            properties = get_upload_provider().inspect(upload.staging_key)
        except UploadMissing:
            return GenericFuncResp(False, FailureMessage.UPLOAD_MISSING, status_code=409)
        except (StorageUnavailable, OSError):
            logger.exception('Could not inspect upload %s', upload.public_id)

            return GenericFuncResp(False, FailureMessage.UPLOAD_UNAVAILABLE, status_code=503)

        if properties['size'] != upload.expected_size:
            cls.get_uploads(public_id=public_id).filter(status='pending').update(
                status='rejected', error=FailureMessage.UPLOAD_SIZE_MISMATCH
            )

            return GenericFuncResp(False, FailureMessage.UPLOAD_SIZE_MISMATCH, status_code=400)

        cls.get_uploads(public_id=public_id).filter(status='pending').update(
            status='validating',
            actual_size=properties['size'],
            storage_version=properties['etag'],
            next_attempt_at=timezone.now(),
        )
        result = cls.status(user, public_id)
        result.status_code = 202

        return result

    @classmethod
    def receive_local(cls, user, public_id, token, stream, size):
        if settings.NOD_STORAGE_PROVIDER != 'local' or not settings.DEBUG:
            return GenericFuncResp(False, FailureMessage.UPLOAD_NOT_FOUND, status_code=404)

        try:
            claims = signing.loads(token, salt=UPLOAD_TOKEN_SALT, max_age=UPLOAD_URL_TTL)
        except signing.BadSignature:
            return GenericFuncResp(False, FailureMessage.UPLOAD_EXPIRED, status_code=403)

        if claims != {'upload_id': str(public_id), 'owner_id': user.pk}:
            return GenericFuncResp(False, FailureMessage.UPLOAD_NOT_FOUND, status_code=404)

        with transaction.atomic():
            upload = cls.get_uploads(owner=user, public_id=public_id).select_for_update().first()

            if upload is None:
                return GenericFuncResp(False, FailureMessage.UPLOAD_NOT_FOUND, status_code=404)

            if upload.status != 'pending' or upload.upload_expires_at <= timezone.now():
                return GenericFuncResp(False, FailureMessage.UPLOAD_EXPIRED, status_code=410)

            if size != upload.expected_size:
                return GenericFuncResp(False, FailureMessage.UPLOAD_SIZE_MISMATCH, status_code=400)

            storage = get_document_storage()

            if storage.exists(upload.staging_key):
                return GenericFuncResp(False, FailureMessage.UPLOAD_USED, status_code=409)

            content = stream.read(upload.expected_size + 1)

            if len(content) != upload.expected_size:
                return GenericFuncResp(False, FailureMessage.UPLOAD_SIZE_MISMATCH, status_code=400)

            storage.save(upload.staging_key, ContentFile(content))

        return GenericFuncResp(True, status_code=201)
