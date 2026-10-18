import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def move_content_type(apps, schema_editor):
    apps.get_model('contenttypes', 'ContentType').objects.using(
        schema_editor.connection.alias
    ).filter(app_label='nod_submission_service', model='documentupload').update(
        app_label='nod_upload_service'
    )


def restore_content_type(apps, schema_editor):
    apps.get_model('contenttypes', 'ContentType').objects.using(
        schema_editor.connection.alias
    ).filter(app_label='nod_upload_service', model='documentupload').update(
        app_label='nod_submission_service'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('nod_submission_service', '0003_documentupload'),
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='DocumentUpload',
                    fields=[
                        (
                            'id',
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name='ID',
                            ),
                        ),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        (
                            'public_id',
                            models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                        ),
                        ('staging_key', models.CharField(max_length=512, unique=True)),
                        ('final_key', models.CharField(blank=True, default='', max_length=512)),
                        ('original_name', models.CharField(max_length=255)),
                        ('expected_size', models.PositiveIntegerField()),
                        ('actual_size', models.PositiveIntegerField(default=0)),
                        ('content_type', models.CharField(max_length=128)),
                        ('checksum', models.CharField(blank=True, default='', max_length=64)),
                        (
                            'storage_version',
                            models.CharField(blank=True, default='', max_length=256),
                        ),
                        (
                            'status',
                            models.CharField(
                                choices=[
                                    ('pending', 'Pending'),
                                    ('validating', 'Validating'),
                                    ('ready', 'Ready'),
                                    ('rejected', 'Rejected'),
                                    ('attached', 'Attached'),
                                    ('expired', 'Expired'),
                                ],
                                default='pending',
                                max_length=16,
                            ),
                        ),
                        ('error', models.CharField(blank=True, default='', max_length=300)),
                        ('upload_expires_at', models.DateTimeField()),
                        ('expires_at', models.DateTimeField()),
                        ('next_attempt_at', models.DateTimeField(null=True)),
                        ('lease_expires_at', models.DateTimeField(null=True)),
                        ('lease_token', models.UUIDField(null=True)),
                        ('attempts', models.PositiveSmallIntegerField(default=0)),
                        ('cleaned_at', models.DateTimeField(null=True)),
                        (
                            'owner',
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name='document_uploads',
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            'submission',
                            models.OneToOneField(
                                null=True,
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name='upload',
                                to='nod_submission_service.submission',
                            ),
                        ),
                    ],
                    options={
                        'db_table': 'nod_document_uploads',
                        'indexes': [
                            models.Index(
                                fields=['status', 'next_attempt_at'],
                                name='nod_documen_status_ee3551_idx',
                            ),
                            models.Index(
                                fields=['owner', 'status'], name='nod_documen_owner_i_c34232_idx'
                            ),
                            models.Index(
                                fields=['expires_at', 'cleaned_at'],
                                name='nod_documen_expires_7694ff_idx',
                            ),
                        ],
                        'constraints': [
                            models.CheckConstraint(
                                condition=models.Q(
                                    (
                                        'status__in',
                                        [
                                            'pending',
                                            'validating',
                                            'ready',
                                            'rejected',
                                            'attached',
                                            'expired',
                                        ],
                                    )
                                ),
                                name='nod_valid_upload_status',
                            ),
                            models.CheckConstraint(
                                condition=models.Q(
                                    models.Q(('status', 'attached'), ('submission__isnull', False)),
                                    models.Q(
                                        models.Q(('status', 'attached'), _negated=True),
                                        ('submission__isnull', True),
                                    ),
                                    _connector='OR',
                                ),
                                name='nod_upload_attachment',
                            ),
                            models.CheckConstraint(
                                condition=models.Q(
                                    models.Q(('status__in', ['ready', 'attached']), _negated=True),
                                    models.Q(
                                        models.Q(('final_key', ''), _negated=True),
                                        models.Q(('checksum', ''), _negated=True),
                                        ('actual_size__gt', 0),
                                    ),
                                    _connector='OR',
                                ),
                                name='nod_upload_validated_file',
                            ),
                        ],
                    },
                ),
            ],
        ),
        migrations.RunPython(move_content_type, restore_content_type),
    ]
