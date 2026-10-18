"""OpenAPI response contracts and annotations shared by the API views."""

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_serializer,
    inline_serializer,
)
from rest_framework import serializers

from nod_auth_service.serializers import UserSerializer
from nod_submission_service.serializers import SubmissionDetailSerializer, SubmissionSerializer
from nod_submission_service.serializers import SubmissionEventSerializer


def shape(component_name, **fields):
    return inline_serializer(name=component_name, fields=fields)


def envelope(name, data=None):
    fields = {
        'status': serializers.BooleanField(),
        'message': serializers.CharField(required=False),
    }
    if data is not None:
        fields['data'] = data
    result = shape(name, **fields)
    extend_schema_serializer(many=False)(result.__class__)
    return result


ERROR = shape(
    'ApiError',
    status=serializers.BooleanField(),
    message=serializers.CharField(),
    errors=serializers.JSONField(required=False),
)
MESSAGE = envelope('MessageResponse')
USER = envelope('UserResponse', UserSerializer())
USERS = envelope('ReviewersResponse', UserSerializer(many=True))
BOOTSTRAP = envelope(
    'BootstrapResponse',
    shape('Bootstrap', csrf_token=serializers.CharField(), demo_enabled=serializers.BooleanField()),
)
AUTH = envelope(
    'AuthResponse', shape('AuthSession', user=UserSerializer(), csrf_token=serializers.CharField())
)
CHALLENGE = envelope(
    'ChallengeResponse',
    shape(
        'Challenge',
        challenge_id=serializers.UUIDField(),
        expires_in=serializers.IntegerField(),
        resend_after=serializers.IntegerField(),
    ),
)
UPLOAD = envelope(
    'UploadResponse',
    shape(
        'UploadInstruction',
        upload_id=serializers.UUIDField(),
        upload_url=serializers.CharField(),
        method=serializers.ChoiceField(choices=['PUT']),
        headers=serializers.DictField(child=serializers.CharField()),
        expires_in=serializers.IntegerField(),
        local=serializers.BooleanField(),
    ),
)
UPLOAD_STATE = envelope(
    'UploadStateResponse',
    shape(
        'UploadState',
        upload_id=serializers.UUIDField(),
        status=serializers.ChoiceField(
            choices=['pending', 'validating', 'ready', 'rejected', 'attached', 'expired']
        ),
        error=serializers.CharField(allow_blank=True),
        name=serializers.CharField(),
    ),
)
SUBMISSION = envelope('SubmissionResponse', SubmissionDetailSerializer())
SUBMISSIONS = envelope(
    'SubmissionPageResponse',
    shape(
        'SubmissionPage',
        results=SubmissionSerializer(many=True),
        count=serializers.IntegerField(),
        page=serializers.IntegerField(),
        pages=serializers.IntegerField(),
    ),
)
HISTORY = envelope('HistoryResponse', SubmissionEventSerializer(many=True))
SUMMARY = envelope(
    'SummaryResponse',
    shape(
        'SubmissionSummary',
        pending=serializers.IntegerField(),
        approved=serializers.IntegerField(),
        rejected=serializers.IntegerField(),
        total=serializers.IntegerField(),
        oldest_pending_at=serializers.DateTimeField(allow_null=True),
    ),
)
FILE_LINK = envelope(
    'FileLinkResponse',
    shape(
        'FileLink',
        url=serializers.CharField(),
        expires_in=serializers.IntegerField(),
        content_type=serializers.CharField(),
    ),
)
SCOPE = OpenApiParameter('scope', str, enum=['mine', 'assigned'], default='mine')
TOKEN = OpenApiParameter(
    'token', str, required=True, description='Token from the signed local URL.'
)


def example(name, value):
    return OpenApiExample(name, value=value, request_only=True)


def operation(
    name, tag, summary, response, *, request=None, code=200, also_codes=(), errors=(), **kwargs
):
    """Keep actual JSON envelopes explicit instead of inferring flat model responses."""
    responses = {code: response, **{status: ERROR for status in errors}}
    responses.update({status: response for status in also_codes})
    return extend_schema(
        operation_id=name,
        tags=[tag],
        summary=summary,
        request=request,
        responses=responses,
        **kwargs,
    )
