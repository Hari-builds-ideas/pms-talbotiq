from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE TRIGGER audit_log_block_update "
                "BEFORE UPDATE ON audit_log FOR EACH ROW "
                "SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'audit_log is append-only: UPDATE is forbidden';"
            ),
            reverse_sql="DROP TRIGGER IF EXISTS audit_log_block_update;",
        ),
        migrations.RunSQL(
            sql=(
                "CREATE TRIGGER audit_log_block_delete "
                "BEFORE DELETE ON audit_log FOR EACH ROW "
                "SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'audit_log is append-only: DELETE is forbidden';"
            ),
            reverse_sql="DROP TRIGGER IF EXISTS audit_log_block_delete;",
        ),
    ]
