from django.db import migrations, models


def enable_verified_reviewers(apps, schema_editor):
    User = apps.get_model('nod_auth_service', 'User')
    User.objects.using(schema_editor.connection.alias).filter(
        is_active=True, email_verified=True, can_review=False
    ).update(can_review=True)


class Migration(migrations.Migration):
    dependencies = [('nod_auth_service', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='user', name='can_review', field=models.BooleanField(default=True)
        ),
        migrations.RunPython(enable_verified_reviewers, migrations.RunPython.noop),
    ]
