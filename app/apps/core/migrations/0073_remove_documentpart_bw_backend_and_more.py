# Generated by Django 4.1.13 on 2024-05-30 16:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0072_transcription_comments'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='documentpart',
            name='bw_backend',
        ),
        migrations.RemoveField(
            model_name='documentpart',
            name='bw_image',
        ),
    ]
