# Generated migration for append_ops_remark field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('work_tools2', '0011_formconfig_query_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='formconfig',
            name='append_ops_remark',
            field=models.BooleanField(default=True, verbose_name='是否拼接操作备注'),
        ),
    ]
