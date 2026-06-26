from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0003_securityevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                max_length=100,
                choices=[
                    ("login", "Login"),
                    ("logout", "Logout"),
                    ("failed_login", "Failed Login"),
                    ("view_document", "View Document"),
                    ("download_document", "Download Document"),
                    ("upload_document", "Upload Document"),
                    ("delete_document", "Delete Document"),
                    ("restore_document", "Restore Document"),
                    ("update_document", "Update Document"),
                    ("permission_change", "Permission Change"),
                    ("create_share", "Create Share"),
                    ("create_folder", "Create Folder"),
                    ("mfa_enabled", "MFA Enabled"),
                    ("export_package", "Export Package"),
                ],
            ),
        ),
    ]
