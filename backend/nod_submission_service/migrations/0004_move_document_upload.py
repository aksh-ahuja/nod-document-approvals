from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('nod_submission_service', '0003_documentupload'),
        ('nod_upload_service', '0001_move_document_upload'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.DeleteModel(name='DocumentUpload')],
        ),
    ]
