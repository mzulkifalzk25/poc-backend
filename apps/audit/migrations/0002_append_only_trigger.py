from django.db import migrations

CREATE_TRIGGER = """
    CREATE OR REPLACE FUNCTION audit_activitylog_block_update_delete()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_activitylog rows are append-only: % is not allowed', TG_OP;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER audit_activitylog_append_only
    BEFORE UPDATE OR DELETE ON audit_activitylog
    FOR EACH ROW EXECUTE FUNCTION audit_activitylog_block_update_delete();
"""

DROP_TRIGGER = """
    DROP TRIGGER IF EXISTS audit_activitylog_append_only ON audit_activitylog;
    DROP FUNCTION IF EXISTS audit_activitylog_block_update_delete();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
