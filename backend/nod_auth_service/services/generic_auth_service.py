import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from utils.dto import GenericFuncResp
from utils.email.factory import get_email_provider
from utils.email.exceptions import EmailDeliveryError

from ..models import User, RegistrationChallenge, AuthRateLimit
from ..constants import (
    OTP_DIGITS,
    OTP_TTL_SECONDS,
    OTP_RESEND_SECONDS,
    OTP_MAX_ATTEMPTS,
    OTP_EMAIL_HOURLY_LIMIT,
    OTP_IP_HOURLY_LIMIT,
    LOGIN_HOURLY_LIMIT,
    RATE_WINDOW_SECONDS,
)
from ..messages import FailureMessage, SuccessMessage

logger = logging.getLogger(__name__)


class GenericAuthService:
    @classmethod
    def get_users(cls, public_id=None, can_review=None, is_active=True):
        users = User.objects.filter(is_active=is_active, email_verified=True)

        if public_id is not None:
            users = users.filter(public_id=public_id)

        if can_review is not None:
            users = users.filter(can_review=can_review)

        return users

    @classmethod
    @transaction.atomic
    def take_rate_slot(cls, key, limit):
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        rate, _ = AuthRateLimit.objects.get_or_create(
            key=key_hash, defaults={'window_started_at': timezone.now()}
        )
        rate = AuthRateLimit.objects.select_for_update().get(pk=rate.pk)

        if rate.window_started_at + timedelta(seconds=RATE_WINDOW_SECONDS) <= timezone.now():
            rate.window_started_at = timezone.now()
            rate.count = 0

        if rate.count >= limit:
            return False

        rate.count += 1
        rate.save(update_fields=['count', 'window_started_at', 'updated_at'])

        return True

    @classmethod
    def __hash_code(cls, public_id, code):
        return hmac.new(
            settings.SECRET_KEY.encode(), f'{public_id}:{code}'.encode(), hashlib.sha256
        ).hexdigest()

    @classmethod
    def register(cls, name, email, password, ip):
        if not cls.take_rate_slot(f'register-ip:{ip}', OTP_IP_HOURLY_LIMIT):
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        if not cls.take_rate_slot(f'otp-email:{email}', OTP_EMAIL_HOURLY_LIMIT):
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        code = f'{secrets.randbelow(10 ** OTP_DIGITS):0{OTP_DIGITS}d}'
        result = cls.__prepare_challenge(name, email, make_password(password), code)

        if not result.success:
            return result

        return cls.__deliver_code(result.data, code)

    @classmethod
    @transaction.atomic
    def __prepare_challenge(cls, name, email, password_hash, code):
        if User.objects.filter(email=email).exists():
            return GenericFuncResp(False, FailureMessage.EXISTING_ACCOUNT, status_code=409)

        now = timezone.now()
        challenge, created = RegistrationChallenge.objects.get_or_create(
            email=email,
            defaults={
                'name': name,
                'password_hash': password_hash,
                'code_hash': '',
                'sent_at': now,
                'expires_at': now,
            },
        )
        challenge = RegistrationChallenge.objects.select_for_update().get(pk=challenge.pk)

        if not created and challenge.sent_at + timedelta(seconds=OTP_RESEND_SECONDS) > now:
            return GenericFuncResp(False, FailureMessage.RESEND_WAIT, status_code=429)

        if not created and challenge.attempts >= OTP_MAX_ATTEMPTS and challenge.expires_at > now:
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        challenge.public_id = uuid.uuid4()
        challenge.name = name
        challenge.password_hash = password_hash
        challenge.code_hash = cls.__hash_code(challenge.public_id, code)

        if challenge.expires_at <= now:
            challenge.attempts = 0

        challenge.sent_at = now
        challenge.expires_at = now + timedelta(seconds=OTP_TTL_SECONDS)
        challenge.consumed_at = None
        challenge.save()

        return GenericFuncResp(True, data=challenge)

    @classmethod
    def __deliver_code(cls, challenge, code):
        try:
            get_email_provider().send_otp(challenge.email, code)
        except EmailDeliveryError:
            logger.warning('OTP delivery failed for challenge %s', challenge.public_id)
            RegistrationChallenge.objects.filter(
                public_id=challenge.public_id, code_hash=challenge.code_hash
            ).update(expires_at=timezone.now())

            return GenericFuncResp(False, FailureMessage.EMAIL_FAILED, status_code=503)

        return GenericFuncResp(
            True,
            SuccessMessage.CODE_SENT,
            {
                'challenge_id': str(challenge.public_id),
                'expires_in': OTP_TTL_SECONDS,
                'resend_after': OTP_RESEND_SECONDS,
            },
            202,
        )

    @classmethod
    def resend(cls, challenge_id, ip):
        if not cls.take_rate_slot(f'register-ip:{ip}', OTP_IP_HOURLY_LIMIT):
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        challenge = RegistrationChallenge.objects.filter(
            public_id=challenge_id, consumed_at__isnull=True
        ).first()

        if challenge is None:
            return GenericFuncResp(False, FailureMessage.INVALID_CODE, status_code=400)

        if not cls.take_rate_slot(f'otp-email:{challenge.email}', OTP_EMAIL_HOURLY_LIMIT):
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        code = f'{secrets.randbelow(10 ** OTP_DIGITS):0{OTP_DIGITS}d}'
        result = cls.__rotate_code(challenge_id, code)

        if not result.success:
            return result

        return cls.__deliver_code(result.data, code)

    @classmethod
    @transaction.atomic
    def __rotate_code(cls, challenge_id, code):
        challenge = (
            RegistrationChallenge.objects.select_for_update()
            .filter(public_id=challenge_id, consumed_at__isnull=True)
            .first()
        )

        if challenge is None:
            return GenericFuncResp(False, FailureMessage.INVALID_CODE, status_code=400)

        now = timezone.now()

        if challenge.sent_at + timedelta(seconds=OTP_RESEND_SECONDS) > now:
            return GenericFuncResp(False, FailureMessage.RESEND_WAIT, status_code=429)

        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        challenge.public_id = uuid.uuid4()
        challenge.code_hash = cls.__hash_code(challenge.public_id, code)
        challenge.sent_at = now
        challenge.expires_at = now + timedelta(seconds=OTP_TTL_SECONDS)
        challenge.save()

        return GenericFuncResp(True, data=challenge)

    @classmethod
    def verify(cls, challenge_id, code, ip):
        if not cls.take_rate_slot(f'verify-ip:{ip}', LOGIN_HOURLY_LIMIT):
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        return cls.__consume_code(challenge_id, code)

    @classmethod
    @transaction.atomic
    def __consume_code(cls, challenge_id, code):
        challenge = (
            RegistrationChallenge.objects.select_for_update().filter(public_id=challenge_id).first()
        )

        if challenge is None or challenge.consumed_at or challenge.expires_at <= timezone.now():
            return GenericFuncResp(False, FailureMessage.INVALID_CODE, status_code=400)

        if challenge.attempts >= OTP_MAX_ATTEMPTS:
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        challenge.attempts += 1
        challenge.save(update_fields=['attempts', 'updated_at'])

        if not hmac.compare_digest(challenge.code_hash, cls.__hash_code(challenge.public_id, code)):
            return GenericFuncResp(False, FailureMessage.INVALID_CODE, status_code=400)

        if User.objects.filter(email=challenge.email).exists():
            return GenericFuncResp(False, FailureMessage.EXISTING_ACCOUNT, status_code=409)

        user = User.objects.create(
            email=challenge.email,
            name=challenge.name,
            password=challenge.password_hash,
            email_verified=True,
            can_review=True,
        )
        challenge.consumed_at = timezone.now()
        challenge.password_hash = ''
        challenge.code_hash = ''
        challenge.save()

        return GenericFuncResp(True, SuccessMessage.VERIFIED, user, 201)

    @classmethod
    def login(cls, email, password, ip):
        ip_allowed = cls.take_rate_slot(f'login-ip:{ip}', LOGIN_HOURLY_LIMIT)
        email_allowed = cls.take_rate_slot(f'login-email:{email}', LOGIN_HOURLY_LIMIT)

        if not ip_allowed or not email_allowed:
            return GenericFuncResp(False, FailureMessage.TOO_MANY_ATTEMPTS, status_code=429)

        user = authenticate(email=email, password=password)

        if user is None or not user.email_verified:
            return GenericFuncResp(False, FailureMessage.INVALID_LOGIN, status_code=401)

        return GenericFuncResp(True, data=user)

    @classmethod
    @transaction.atomic
    def grant_reviewer(cls, email):
        return User.objects.filter(email=email.lower(), is_active=True, email_verified=True).update(
            can_review=True
        )

    @classmethod
    @transaction.atomic
    def seed_demo_users(cls):
        if not settings.NOD_ENABLE_DEMO:
            raise ValueError('Demo accounts are disabled.')

        users = []

        for email, name, review in [
            ('jamie@nod.demo', 'Jamie Morgan', True),
            ('alex@nod.demo', 'Alex Rivera', True),
            ('sam@nod.demo', 'Sam Chen', True),
        ]:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'name': name,
                    'can_review': review,
                    'email_verified': True,
                },
            )

            if created:
                user.set_password('NodDemo!2026')
                user.save()

            users.append(user)

        return users

    @classmethod
    @transaction.atomic
    def cleanup_expired_auth(cls):
        cutoff = timezone.now() - timedelta(days=1)
        challenges, _ = RegistrationChallenge.objects.filter(expires_at__lt=cutoff).delete()
        limits, _ = AuthRateLimit.objects.filter(window_started_at__lt=cutoff).delete()

        return challenges, limits
