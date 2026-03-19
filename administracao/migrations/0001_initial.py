from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ADConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("server_host", models.CharField(max_length=255)),
                ("server_port", models.PositiveIntegerField(default=389)),
                ("use_ssl", models.BooleanField(default=False)),
                ("base_dn", models.CharField(max_length=255)),
                ("bind_dn", models.CharField(max_length=255)),
                ("bind_password", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuracao de AD",
                "verbose_name_plural": "Configuracoes de AD",
            },
        ),
    ]
