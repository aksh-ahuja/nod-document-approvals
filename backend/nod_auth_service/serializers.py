from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers

from .constants import NAME_MAX_LENGTH, EMAIL_MAX_LENGTH, OTP_DIGITS
from .models import User


class RegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=NAME_MAX_LENGTH)
    email = serializers.EmailField(max_length=EMAIL_MAX_LENGTH)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        attrs['email'] = attrs['email'].lower()

        try:
            validate_password(attrs['password'], User(email=attrs['email'], name=attrs['name']))
        except ValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc

        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=EMAIL_MAX_LENGTH)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_email(self, value):
        return value.lower()


class VerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.RegexField(r'^\d{6}$', min_length=OTP_DIGITS, max_length=OTP_DIGITS)


class ResendSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='public_id')

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'can_review']
