# Generated for link-import projects without an uploaded PDF.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('studio', '0008_alter_job_kind'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='pdf_file',
            field=models.FileField(blank=True, null=True, upload_to='projects/pdfs/'),
        ),
    ]
