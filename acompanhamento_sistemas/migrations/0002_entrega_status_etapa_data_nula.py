from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acompanhamento_sistemas", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="entregasistema",
            name="status",
            field=models.CharField(
                choices=[("RASCUNHO", "Rascunho"), ("PUBLICADO", "Publicado")],
                default="RASCUNHO",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="etapasistema",
            name="data_etapa",
            field=models.DateField(blank=True, null=True),
        ),
    ]
