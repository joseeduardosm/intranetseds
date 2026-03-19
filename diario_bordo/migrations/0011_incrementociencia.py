"""
Cria modelo IncrementoCiencia para confirmação de ciência.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    """Representa uma etapa versionada de evolução de schema do app."""

    dependencies = [
        ("diario_bordo", "0010_remove_blocotrabalho_historico"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IncrementoCiencia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("texto", models.TextField()),
                ("criado_em", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "incremento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ciencias",
                        to="diario_bordo.incremento",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incrementos_ciencias",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["criado_em"],
                "unique_together": {("incremento", "usuario")},
            },
        ),
    ]
