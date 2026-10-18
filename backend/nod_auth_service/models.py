import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

from utils.abstract_models import TimeStampedModel

from .constants import NAME_MAX_LENGTH, EMAIL_MAX_LENGTH, HASH_MAX_LENGTH


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.update(is_staff=True, is_superuser=True, can_review=True, email_verified=True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser, TimeStampedModel):
    username = None
    first_name = None
    last_name = None
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(max_length=EMAIL_MAX_LENGTH, unique=True)
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    can_review = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'nod_users'
        constraints = [models.UniqueConstraint(Lower('email'), name='nod_unique_email_ci')]


class RegistrationChallenge(TimeStampedModel):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True)
    email = models.EmailField(max_length=EMAIL_MAX_LENGTH, unique=True)
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    password_hash = models.CharField(max_length=HASH_MAX_LENGTH)
    code_hash = models.CharField(max_length=HASH_MAX_LENGTH)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = 'nod_registration_challenges'


class AuthRateLimit(TimeStampedModel):
    key = models.CharField(max_length=HASH_MAX_LENGTH, unique=True)
    window_started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'nod_auth_rate_limits'
