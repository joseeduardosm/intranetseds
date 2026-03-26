from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sala_situacao_v2", "0009_indicador_processo_entrega_criado_por"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="entrega",
            name="monitorado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="sala_situacao_v2_entregas_monitoradas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
