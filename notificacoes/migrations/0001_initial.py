from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DesktopAPIToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_prefix", models.CharField(db_index=True, max_length=12)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="desktop_api_tokens", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Token da API desktop",
                "verbose_name_plural": "Tokens da API desktop",
                "ordering": ["-id"],
            },
        ),
        migrations.CreateModel(
            name="NotificacaoUsuario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_app", models.CharField(max_length=50)),
                ("event_type", models.CharField(max_length=60)),
                ("title", models.CharField(max_length=160)),
                ("body_short", models.CharField(max_length=500)),
                ("target_url", models.CharField(max_length=500)),
                ("dedupe_key", models.CharField(blank=True, default="", max_length=255)),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("displayed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notificacoes_desktop", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Notificacao de usuario",
                "verbose_name_plural": "Notificacoes de usuario",
                "ordering": ["-id"],
            },
        ),
        migrations.AddIndex(
            model_name="notificacaousuario",
            index=models.Index(fields=["user", "id"], name="notificacoe_user_id_dc6315_idx"),
        ),
        migrations.AddIndex(
            model_name="notificacaousuario",
            index=models.Index(fields=["user", "created_at"], name="notificacoe_user_cr_1daa90_idx"),
        ),
        migrations.AddIndex(
            model_name="notificacaousuario",
            index=models.Index(fields=["user", "read_at"], name="notificacoe_user_re_baa0bc_idx"),
        ),
        migrations.AddIndex(
            model_name="notificacaousuario",
            index=models.Index(fields=["user", "displayed_at"], name="notificacoe_user_di_4ebe14_idx"),
        ),
        migrations.AddIndex(
            model_name="notificacaousuario",
            index=models.Index(fields=["user", "dedupe_key", "created_at"], name="notificacoe_user_de_1ef85f_idx"),
        ),
    ]
