from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers

from nod_auth_service.serializers import UserSerializer

from .models import Submission, SubmissionEvent
from .constants import TITLE_MAX_LENGTH, CONTENT_MAX_LENGTH, NOTE_MAX_LENGTH, SEARCH_MAX_LENGTH
from .messages import FailureMessage


class CreateSubmissionSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=TITLE_MAX_LENGTH)
    content = serializers.CharField(
        max_length=CONTENT_MAX_LENGTH, required=False, allow_blank=True, default=''
    )
    upload_id = serializers.UUIDField(required=False)
    reviewer_id = serializers.UUIDField()
    client_request_id = serializers.UUIDField()

    def validate(self, attrs):
        if 'file' in self.initial_data:
            raise serializers.ValidationError({'file': FailureMessage.UPLOAD_LEGACY})

        if not attrs.get('content') and not attrs.get('upload_id'):
            raise serializers.ValidationError({'content': FailureMessage.CONTENT_REQUIRED})

        if attrs.get('content') and attrs.get('upload_id'):
            raise serializers.ValidationError({'file': FailureMessage.CONTENT_CONFLICT})

        return attrs


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    note = serializers.CharField(
        max_length=NOTE_MAX_LENGTH, required=False, allow_blank=True, default=''
    )

    def validate(self, attrs):
        if attrs['decision'] == 'rejected' and not attrs['note']:
            raise serializers.ValidationError({'note': FailureMessage.NOTE_REQUIRED})

        return attrs


class SubmissionQuerySerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=['mine', 'assigned'], default='mine')
    status = serializers.ChoiceField(choices=['pending', 'approved', 'rejected'], required=False)
    search = serializers.CharField(max_length=SEARCH_MAX_LENGTH, required=False, allow_blank=True)


class SubmissionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='public_id')
    submitter = UserSerializer()
    assigned_reviewer = UserSerializer()
    file = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            'type': 'object',
            'nullable': True,
            'properties': {
                'name': {'type': 'string'},
                'size': {'type': 'integer'},
                'content_type': {'type': 'string'},
            },
            'required': ['name', 'size', 'content_type'],
        }
    )
    def get_file(self, submission):
        if not submission.file_key:
            return None

        return {
            'name': submission.file_name,
            'size': submission.file_size,
            'content_type': submission.file_content_type,
        }

    class Meta:
        model = Submission
        fields = [
            'id',
            'title',
            'status',
            'submitter',
            'assigned_reviewer',
            'created_at',
            'decided_at',
            'file',
        ]


class SubmissionDetailSerializer(SubmissionSerializer):
    class Meta(SubmissionSerializer.Meta):
        fields = SubmissionSerializer.Meta.fields + ['content']


class SubmissionEventSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='public_id')
    actor = UserSerializer()

    class Meta:
        model = SubmissionEvent
        fields = [
            'id',
            'actor',
            'event_type',
            'previous_status',
            'new_status',
            'note',
            'created_at',
        ]
