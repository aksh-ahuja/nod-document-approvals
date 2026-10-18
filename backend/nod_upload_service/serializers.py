from pathlib import Path

from rest_framework import serializers

from utils.storage.constants import FILE_NAME_MAX_LENGTH, FILE_TYPE_MAX_LENGTH, FILE_TYPES

from .constants import FILE_MAX_BYTES
from .messages import FailureMessage


class CreateUploadSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=FILE_NAME_MAX_LENGTH)
    size = serializers.IntegerField(min_value=1, max_value=FILE_MAX_BYTES)
    content_type = serializers.CharField(
        max_length=FILE_TYPE_MAX_LENGTH, required=False, allow_blank=True
    )

    def validate_filename(self, value):
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise serializers.ValidationError(FailureMessage.FILE_INVALID)

        if '/' in value or '\\' in value:
            raise serializers.ValidationError(FailureMessage.FILE_INVALID)

        if Path(value).suffix.lower() not in FILE_TYPES:
            raise serializers.ValidationError(FailureMessage.FILE_TYPE)

        return value
