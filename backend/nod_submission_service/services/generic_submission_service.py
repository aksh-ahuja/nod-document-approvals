import hashlib
import json
import logging
import uuid
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from nod_auth_service.services import GenericAuthService
from nod_upload_service.services import GenericUploadService
from utils.dto import GenericFuncResp
from utils.storage.constants import FILE_TYPES
from utils.storage.factory import get_cloud_file_url, get_document_storage
from utils.storage.preview import PreviewUnavailable, convert_docx

from ..constants import FILE_LINK_SALT, FILE_LINK_TTL
from ..messages import FailureMessage, SuccessMessage
from ..models import Submission, SubmissionEvent

logger = logging.getLogger(__name__)


class GenericSubmissionService:

    @classmethod
    def get_submissions(cls, user, scope=None, status=None, search=None):
        submissions = Submission.objects.select_related('submitter', 'assigned_reviewer')

        if scope == 'mine':
            submissions = submissions.filter(submitter=user)
        elif scope == 'assigned':
            submissions = (
                submissions.filter(assigned_reviewer=user)
                if user.can_review
                else submissions.none()
            )
        else:
            access = Q(submitter=user)

            if user.can_review:
                access |= Q(assigned_reviewer=user)

            submissions = submissions.filter(access)

        if status:
            submissions = submissions.filter(status=status)

        if search:
            submissions = submissions.filter(
                Q(title__icontains=search)
                | Q(submitter__name__icontains=search)
                | Q(assigned_reviewer__name__icontains=search)
            )

        if scope == 'assigned' and status == 'pending':
            return submissions.order_by('created_at', 'id')

        return submissions.order_by('-created_at', '-id')

    @classmethod
    @transaction.atomic
    def create_submission(
        cls, user, title, content, reviewer_id, client_request_id, upload_id=None
    ):
        request_hash = cls.__get_request_hash(title, content, reviewer_id, upload_id)
        GenericAuthService.get_users(public_id=user.public_id).select_for_update().get()
        previous = Submission.objects.filter(
            submitter=user, client_request_id=client_request_id
        ).first()

        if previous:
            if previous.request_hash != request_hash:
                return GenericFuncResp(False, FailureMessage.REQUEST_CONFLICT, status_code=409)

            return GenericFuncResp(True, data=previous)

        reviewer = (
            GenericAuthService.get_users(public_id=reviewer_id, can_review=True)
            .exclude(pk=user.pk)
            .first()
        )

        if reviewer is None:
            return GenericFuncResp(False, FailureMessage.INVALID_REVIEWER, status_code=400)

        upload = None

        if upload_id:
            result = GenericUploadService.get_ready_upload(user, upload_id)

            if not result.success:
                return result

            upload = result.data

        submission = Submission.objects.create(
            submitter=user,
            assigned_reviewer=reviewer,
            title=title,
            content=content,
            client_request_id=client_request_id,
            request_hash=request_hash,
            file_key=upload.final_key if upload else '',
            file_name=upload.original_name if upload else '',
            file_size=upload.actual_size if upload else 0,
            file_content_type=upload.content_type if upload else '',
        )
        SubmissionEvent.objects.create(
            submission=submission,
            actor=user,
            event_type='submitted',
            new_status='pending',
        )

        if upload:
            GenericUploadService.attach_to_submission(upload, submission.pk)

        return GenericFuncResp(True, SuccessMessage.SUBMITTED, submission, 201)

    @classmethod
    def __get_request_hash(cls, title, content, reviewer_id, upload_id):
        payload = {'title': title, 'content': content, 'reviewer_id': str(reviewer_id)}

        if upload_id:
            payload['upload_id'] = str(upload_id)

        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @classmethod
    def __remove_failed_upload(cls, storage, key):
        try:
            storage.delete(key)
        except Exception:
            logger.exception('Failed to clean up an uncommitted document upload: %s', key)

    @classmethod
    def __get_preview(cls, submission):
        storage = get_document_storage()
        preview_key = ''

        try:
            with transaction.atomic():
                submission = Submission.objects.select_for_update().get(pk=submission.pk)

                if submission.preview_key:
                    return submission.preview_key

                with storage.open(submission.file_key, 'rb') as original:
                    preview = convert_docx(original)

                preview_key = f'previews/{uuid.uuid4().hex}.pdf'
                preview_key = storage.save(preview_key, preview)
                submission.preview_key = preview_key
                submission.save(update_fields=['preview_key'])

                return preview_key
        except Exception:
            if preview_key:
                cls.__remove_failed_upload(storage, preview_key)

            raise

    @classmethod
    def get_file_link(cls, user, public_id, download=False):
        submission = cls.get_detail(user, public_id)

        if submission is None or not submission.file_key:
            return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

        key = submission.file_key
        filename = submission.file_name
        content_type = submission.file_content_type

        if not download and content_type == FILE_TYPES['.docx']:
            try:
                key = cls.__get_preview(submission)
            except PreviewUnavailable:
                logger.warning('DOCX preview unavailable for submission %s', submission.public_id)

                return GenericFuncResp(False, FailureMessage.PREVIEW_UNAVAILABLE, status_code=503)

            filename = f'{Path(filename).stem}.pdf'
            content_type = FILE_TYPES['.pdf']

        if settings.NOD_STORAGE_PROVIDER == 'local':
            token = signing.dumps(
                {
                    'id': str(submission.public_id),
                    'user': str(user.public_id),
                    'download': download,
                },
                salt=FILE_LINK_SALT,
            )
            url = (
                reverse('nod-submission-content', kwargs={'id': submission.public_id})
                + '?'
                + urlencode({'token': token})
            )
        else:
            url = get_cloud_file_url(key, filename, content_type, download, FILE_LINK_TTL)

        return GenericFuncResp(
            True, data={'url': url, 'expires_in': FILE_LINK_TTL, 'content_type': content_type}
        )

    @classmethod
    def get_local_file(cls, user, public_id, token):
        if settings.NOD_STORAGE_PROVIDER != 'local':
            return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

        try:
            payload = signing.loads(token, salt=FILE_LINK_SALT, max_age=FILE_LINK_TTL)
        except signing.BadSignature:
            return GenericFuncResp(False, FailureMessage.LINK_EXPIRED, status_code=403)

        if payload.get('id') != str(public_id) or payload.get('user') != str(user.public_id):
            return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

        submission = cls.get_detail(user, public_id)

        if submission is None or not submission.file_key:
            return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

        key, filename, content_type = (
            submission.file_key,
            submission.file_name,
            submission.file_content_type,
        )
        download = payload.get('download', False)

        if not download and content_type == FILE_TYPES['.docx']:
            if not submission.preview_key:
                return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

            key, filename, content_type = (
                submission.preview_key,
                f'{Path(filename).stem}.pdf',
                FILE_TYPES['.pdf'],
            )

        try:
            file = get_document_storage().open(key, 'rb')
        except FileNotFoundError:
            return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

        return GenericFuncResp(
            True,
            data={
                'file': file,
                'filename': filename,
                'content_type': content_type,
                'download': download,
            },
        )

    @classmethod
    def get_detail(cls, user, public_id):
        return cls.get_submissions(user).filter(public_id=public_id).first()

    @classmethod
    def get_history(cls, submission):
        return SubmissionEvent.objects.filter(submission=submission).select_related('actor')

    @classmethod
    @transaction.atomic
    def decide(cls, user, public_id, decision, note):
        reviewer = (
            GenericAuthService.get_users(public_id=user.public_id, can_review=True)
            .select_for_update()
            .first()
        )

        if reviewer is None:
            return GenericFuncResp(False, FailureMessage.NOT_ASSIGNED, status_code=403)

        submission = (
            cls.get_submissions(user)
            .select_for_update(of=('self',))
            .filter(public_id=public_id)
            .first()
        )

        if submission is None:
            return GenericFuncResp(False, FailureMessage.NOT_FOUND, status_code=404)

        if submission.assigned_reviewer_id != user.pk or not user.can_review:
            return GenericFuncResp(False, FailureMessage.NOT_ASSIGNED, status_code=403)

        if submission.status != 'pending':
            event = SubmissionEvent.objects.filter(
                submission=submission, event_type=decision, actor=user, note=note
            ).first()

            if event:
                return GenericFuncResp(True, data=submission)

            return GenericFuncResp(False, FailureMessage.ALREADY_DECIDED, status_code=409)

        if decision == 'rejected' and not note.strip():
            return GenericFuncResp(False, FailureMessage.NOTE_REQUIRED, status_code=400)

        submission.status = decision
        submission.decided_at = timezone.now()
        submission.save(update_fields=['status', 'decided_at', 'updated_at'])
        SubmissionEvent.objects.create(
            submission=submission,
            actor=user,
            event_type=decision,
            previous_status='pending',
            new_status=decision,
            note=note,
        )

        return GenericFuncResp(True, SuccessMessage.DECIDED, submission)

    @classmethod
    def summary(cls, user, scope):
        submissions = cls.get_submissions(user, scope=scope)
        counts = {'pending': 0, 'approved': 0, 'rejected': 0}

        for row in submissions.order_by().values('status').annotate(count=Count('pk')):
            counts[row['status']] = row['count']

        counts['total'] = sum(counts.values())
        oldest = submissions.filter(status='pending').order_by('created_at').first()
        counts['oldest_pending_at'] = oldest.created_at if oldest else None

        return counts
