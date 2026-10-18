from django.db import models
from django.db.models import Q, F

from utils.abstract_models import PublicModel

from .constants import (
    TITLE_MAX_LENGTH,
    CONTENT_MAX_LENGTH,
    NOTE_MAX_LENGTH,
    STATUS_MAX_LENGTH,
    HASH_MAX_LENGTH,
    SubmissionStatus,
)
from utils.storage.constants import FILE_KEY_MAX_LENGTH, FILE_NAME_MAX_LENGTH, FILE_TYPE_MAX_LENGTH


class Submission(PublicModel):
    submitter = models.ForeignKey(
        'nod_auth_service.User', on_delete=models.PROTECT, related_name='submissions'
    )
    assigned_reviewer = models.ForeignKey(
        'nod_auth_service.User', on_delete=models.PROTECT, related_name='assigned_submissions'
    )
    title = models.CharField(max_length=TITLE_MAX_LENGTH)
    content = models.TextField(max_length=CONTENT_MAX_LENGTH, blank=True, default='')
    file_key = models.CharField(max_length=FILE_KEY_MAX_LENGTH, blank=True, default='')
    file_name = models.CharField(max_length=FILE_NAME_MAX_LENGTH, blank=True, default='')
    file_size = models.PositiveIntegerField(default=0)
    file_content_type = models.CharField(max_length=FILE_TYPE_MAX_LENGTH, blank=True, default='')
    preview_key = models.CharField(max_length=FILE_KEY_MAX_LENGTH, blank=True, default='')
    status = models.CharField(
        max_length=STATUS_MAX_LENGTH,
        choices=SubmissionStatus.choices(),
        default=SubmissionStatus.PENDING.value,
    )
    decided_at = models.DateTimeField(null=True)
    client_request_id = models.UUIDField()
    request_hash = models.CharField(max_length=HASH_MAX_LENGTH)

    class Meta:
        db_table = 'nod_submissions'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['submitter', '-created_at', '-id']),
            models.Index(fields=['assigned_reviewer', 'status', 'created_at', 'id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['submitter', 'client_request_id'], name='nod_unique_submit_request'
            ),
            models.CheckConstraint(
                condition=~Q(submitter=F('assigned_reviewer')), name='nod_no_self_review'
            ),
            models.CheckConstraint(
                condition=Q(status__in=['pending', 'approved', 'rejected']), name='nod_valid_status'
            ),
            models.CheckConstraint(
                condition=(
                    Q(status='pending', decided_at__isnull=True)
                    | Q(status__in=['approved', 'rejected'], decided_at__isnull=False)
                ),
                name='nod_decision_timestamp',
            ),
            models.CheckConstraint(
                condition=~Q(title='')
                & (
                    (~Q(content='') & Q(file_key=''))
                    | (
                        Q(content='')
                        & ~Q(file_key='')
                        & ~Q(file_name='')
                        & ~Q(file_content_type='')
                        & Q(file_size__gt=0)
                    )
                ),
                name='nod_document_content',
            ),
        ]


class SubmissionEvent(PublicModel):
    submission = models.ForeignKey(
        'nod_submission_service.Submission', on_delete=models.PROTECT, related_name='events'
    )
    actor = models.ForeignKey(
        'nod_auth_service.User', on_delete=models.PROTECT, related_name='submission_events'
    )
    event_type = models.CharField(max_length=STATUS_MAX_LENGTH)
    previous_status = models.CharField(max_length=STATUS_MAX_LENGTH, blank=True)
    new_status = models.CharField(max_length=STATUS_MAX_LENGTH)
    note = models.TextField(max_length=NOTE_MAX_LENGTH, blank=True)

    class Meta:
        db_table = 'nod_submission_events'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['submission', 'created_at', 'id'])]
        constraints = [
            models.UniqueConstraint(
                fields=['submission'],
                condition=Q(event_type__in=['approved', 'rejected']),
                name='nod_one_terminal_decision',
            ),
            models.CheckConstraint(
                condition=Q(event_type__in=['submitted', 'approved', 'rejected']),
                name='nod_valid_event_type',
            ),
        ]
