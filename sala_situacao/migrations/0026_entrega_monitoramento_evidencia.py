"""
Migração de banco: registra mudanças estruturais/evolutivas no schema e dados.

Leitura recomendada para iniciantes: comece pelos itens públicos deste arquivo,
siga para dependências chamadas e confira os testes para observar cenários reais.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    """Representa a estrutura `Migration` no app `sala_situacao`.

    Esta classe concentra regras e comportamentos relacionados ao domínio
    de monitoramento/gestão do painel. Para auditoria, leia os métodos na
    ordem para entender como os dados entram, são validados e persistidos.
    """

    dependencies = [
        ("sala_situacao", "0025_normaliza_textos_indicador_generico"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="entrega",
            name="evidencia_monitoramento",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="sala_situacao/evidencias/%Y/%m/",
                verbose_name="Evidência",
            ),
        ),
        migrations.AddField(
            model_name="entrega",
            name="monitorado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="entrega",
            name="monitorado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="entregas_monitoradas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="entrega",
            options={
                "ordering": ["nome"],
                "permissions": (("monitorar_entrega", "Pode monitorar entrega"),),
            },
        ),
    ]
