from django.db import migrations


def remove_legacy_tables(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS employees_team")
        cursor.execute("DROP TABLE IF EXISTS projects_project")
        cursor.execute(
            """
            DELETE FROM auth_permission
            WHERE content_type_id IN (
                SELECT id
                FROM django_content_type
                WHERE app_label IN ('employees', 'projects')
            )
            """
        )
        cursor.execute(
            """
            UPDATE django_admin_log
            SET content_type_id = NULL
            WHERE content_type_id IN (
                SELECT id
                FROM django_content_type
                WHERE app_label IN ('employees', 'projects')
            )
            """
        )
        cursor.execute(
            "DELETE FROM django_content_type WHERE app_label IN ('employees', 'projects')"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(remove_legacy_tables, migrations.RunPython.noop),
    ]
