# Generated manually: run ANALYZE to populate sqlite_stat1 for fast row counts

from django.db import migrations


def run_analyze(apps, schema_editor):
    """执行 ANALYZE，让 sqlite_stat1 包含各表行数近似值"""
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE")
    except Exception:
        # ANALYZE 失败不影响应用正常运行
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('work_tools2', '0026_remove_attachments_and_migrate_images'),
    ]

    operations = [
        migrations.RunPython(run_analyze, migrations.RunPython.noop),
    ]
