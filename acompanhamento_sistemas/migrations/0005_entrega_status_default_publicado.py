from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("acompanhamento_sistemas", "0004_alter_etapasistema_status_etapaprocessorequisito_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entregasistema",
            name="status",
            field=models.CharField(
                choices=[("RASCUNHO", "Rascunho"), ("PUBLICADO", "Publicado")],
                default="PUBLICADO",
                max_length=20,
            ),
        ),
    ]
