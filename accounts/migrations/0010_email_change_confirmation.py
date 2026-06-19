import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_facebookaccount")]
    operations = [
        migrations.AddField(model_name="customuser", name="pending_email", field=models.EmailField(blank=True, default="", max_length=254)),
        migrations.AddField(model_name="customuser", name="email_change_token", field=models.UUIDField(blank=True, null=True)),
        migrations.AddField(model_name="customuser", name="email_change_token_created_at", field=models.DateTimeField(blank=True, null=True)),
    ]
