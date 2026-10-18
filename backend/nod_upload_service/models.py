from django.db import models
from django.db.models import Q

from utils.abstract_models import PublicModel
from utils.storage.constants import FILE_KEY_MAX_LENGTH, FILE_NAME_MAX_LENGTH, FILE_TYPE_MAX_LENGTH

from .constants import (
    HASH_MAX_LENGTH,
    STATUS_MAX_LENGTH,
    UPLOAD_ETAG_MAX_LENGTH,
    UPLOAD_ERROR_MAX_LENGTH,
    UploadStatus,
)


class DocumentUpload(PublicModel):
    owner = models.ForeignKey(
        'nod_auth_service.User', on_delete=models.PROTECT, related_name='document_uploads'
    )
    submission = models.OneToOneField(
        'nod_submission_service.Submission',
        on_delete=models.PROTECT,
        related_name='upload',
        null=True,
    )
    staging_key = models.CharField(max_length=FILE_KEY_MAX_LENGTH, unique=True)
    final_key = models.CharField(max_length=FILE_KEY_MAX_LENGTH, blank=True, default='')
    original_name = models.CharField(max_length=FILE_NAME_MAX_LENGTH)
    expected_size = models.PositiveIntegerField()
    actual_size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=FILE_TYPE_MAX_LENGTH)
    checksum = models.CharField(max_length=HASH_MAX_LENGTH, blank=True, default='')
    storage_version = models.CharField(max_length=UPLOAD_ETAG_MAX_LENGTH, blank=True, default='')
    status = models.CharField(
        max_length=STATUS_MAX_LENGTH,
        choices=UploadStatus.choices(),
        default=UploadStatus.PENDING.value,
    )
    error = models.CharField(max_length=UPLOAD_ERROR_MAX_LENGTH, blank=True, default='')
    upload_expires_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    next_attempt_at = models.DateTimeField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    lease_token = models.UUIDField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    cleaned_at = models.DateTimeField(null=True)

    class Meta:
        db_table = 'nod_document_uploads'
        indexes = [
            models.Index(fields=['status', 'next_attempt_at']),
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['expires_at', 'cleaned_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[item.value for item in UploadStatus]),
                name='nod_valid_upload_status',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status='attached', submission__isnull=False)
                    | (~Q(status='attached') & Q(submission__isnull=True))
                ),
                name='nod_upload_attachment',
            ),
            models.CheckConstraint(
                condition=~Q(status__in=['ready', 'attached'])
                | (~Q(final_key='') & ~Q(checksum='') & Q(actual_size__gt=0)),
                name='nod_upload_validated_file',
            ),
        ]
