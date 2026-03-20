import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sala_situacao", "0029_processo_indicadores_estrategicos_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotaItemAnexo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arquivo", models.FileField(upload_to="sala_situacao/notas/")),
                ("nome_original", models.CharField(blank=True, default="", max_length=255)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "nota",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="anexos",
                        to="sala_situacao.notaitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Anexo da nota",
                "verbose_name_plural": "Anexos das notas",
                "ordering": ["id"],
            },
        ),
    ]
