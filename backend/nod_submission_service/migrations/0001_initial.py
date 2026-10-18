import django.db.models.deletion

import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Submission',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('content', models.TextField(max_length=50000)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('approved', 'Approved'),
                            ('rejected', 'Rejected'),
                        ],
                        default='pending',
                        max_length=16,
                    ),
                ),
                ('decided_at', models.DateTimeField(null=True)),
                ('client_request_id', models.UUIDField()),
                ('request_hash', models.CharField(max_length=64)),
                (
                    'assigned_reviewer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='assigned_submissions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'submitter',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='submissions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'nod_submissions',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='SubmissionEvent',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                    ),
                ),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('event_type', models.CharField(max_length=16)),
                ('previous_status', models.CharField(blank=True, max_length=16)),
                ('new_status', models.CharField(max_length=16)),
                ('note', models.TextField(blank=True, max_length=2000)),
                (
                    'actor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='submission_events',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'submission',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='events',
                        to='nod_submission_service.submission',
                    ),
                ),
            ],
            options={
                'db_table': 'nod_submission_events',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='submission',
            index=models.Index(
                fields=['submitter', '-created_at', '-id'], name='nod_submiss_submitt_5ffab3_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='submission',
            index=models.Index(
                fields=['assigned_reviewer', 'status', 'created_at', 'id'],
                name='nod_submiss_assigne_8306c4_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.UniqueConstraint(
                fields=('submitter', 'client_request_id'), name='nod_unique_submit_request'
            ),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.CheckConstraint(
                condition=models.Q(('submitter', models.F('assigned_reviewer')), _negated=True),
                name='nod_no_self_review',
            ),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.CheckConstraint(
                condition=models.Q(('status__in', ['pending', 'approved', 'rejected'])),
                name='nod_valid_status',
            ),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(('decided_at__isnull', True), ('status', 'pending')),
                    models.Q(
                        ('decided_at__isnull', False), ('status__in', ['approved', 'rejected'])
                    ),
                    _connector='OR',
                ),
                name='nod_decision_timestamp',
            ),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(('title', ''), _negated=True), models.Q(('content', ''), _negated=True)
                ),
                name='nod_nonempty_content',
            ),
        ),
        migrations.AddIndex(
            model_name='submissionevent',
            index=models.Index(
                fields=['submission', 'created_at', 'id'], name='nod_submiss_submiss_c92027_idx'
            ),
        ),
        migrations.AddConstraint(
            model_name='submissionevent',
            constraint=models.UniqueConstraint(
                condition=models.Q(('event_type__in', ['approved', 'rejected'])),
                fields=('submission',),
                name='nod_one_terminal_decision',
            ),
        ),
        migrations.AddConstraint(
            model_name='submissionevent',
            constraint=models.CheckConstraint(
                condition=models.Q(('event_type__in', ['submitted', 'approved', 'rejected'])),
                name='nod_valid_event_type',
            ),
        ),
    ]
