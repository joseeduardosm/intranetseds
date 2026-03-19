"""
Cria modelo BlocoLeitura para controle de leitura por usuário.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Representa uma etapa versionada de evolução de schema do app."""

    dependencies = [
        ("diario_bordo", "0007_incremento_imagem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BlocoLeitura",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("ultimo_incremento_visto_em", models.DateTimeField(blank=True, null=True)),
                (
                    "bloco",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="leituras",
                        to="diario_bordo.blocotrabalho",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bloco_leituras",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "unique_together": {("usuario", "bloco")},
            },
        ),
    ]
