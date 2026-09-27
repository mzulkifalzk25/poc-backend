from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_user_is_platform_admin"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="is_platform_admin",
            new_name="is_django_admin",
        ),
    ]
