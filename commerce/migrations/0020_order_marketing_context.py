from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0019_order_terms_acceptance_snapshot")]
    operations = [
        migrations.AddField(model_name="order", name="marketing_consent", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="order", name="marketing_context", field=models.JSONField(blank=True, default=dict)),
    ]
