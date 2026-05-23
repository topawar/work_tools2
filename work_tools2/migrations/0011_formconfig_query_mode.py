# Generated migration for adding query_mode field to FormConfig

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work_tools2', '0010_filepathconfig_menu'),
    ]

    operations = [
        migrations.AddField(
            model_name='formconfig',
            name='query_mode',
            field=models.CharField(
                choices=[('strict', '严格模式'), ('loose', '宽松模式')],
                default='strict',
                max_length=20,
                verbose_name='查询模式'
            ),
        ),
    ]
