"""
Migração de banco: registra mudanças estruturais/evolutivas no schema e dados.

Leitura recomendada para iniciantes: comece pelos itens públicos deste arquivo,
siga para dependências chamadas e confira os testes para observar cenários reais.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Representa a estrutura `Migration` no app `sala_situacao`.

    Esta classe concentra regras e comportamentos relacionados ao domínio
    de monitoramento/gestão do painel. Para auditoria, leia os métodos na
    ordem para entender como os dados entram, são validados e persistidos.
    """

    dependencies = [
        ("sala_situacao", "0021_remove_indicadorestrategico_objetivos_estrategicos_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="indicadorestrategico",
            name="tipo_indicador",
            field=models.CharField(
                choices=[
                    ("PROCESSUAL", "Processual"),
                    ("MATEMATICO", "Matemático"),
                    ("MATEMATICO_ACUMULATIVO", "Matemático acumulativo"),
                ],
                default="PROCESSUAL",
                max_length=30,
                verbose_name="Tipo de indicador",
            ),
        ),
        migrations.AlterField(
            model_name="indicadortatico",
            name="tipo_indicador",
            field=models.CharField(
                choices=[
                    ("PROCESSUAL", "Processual"),
                    ("MATEMATICO", "Matemático"),
                    ("MATEMATICO_ACUMULATIVO", "Matemático acumulativo"),
                ],
                default="PROCESSUAL",
                max_length=30,
                verbose_name="Tipo de indicador",
            ),
        ),
        migrations.AddField(
            model_name="indicadorvariavel",
            name="periodicidade_monitoramento",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SEMANAL", "Semanal"),
                    ("QUINZENAL", "Quinzenal"),
                    ("MENSAL", "Mensal"),
                    ("TRIMESTRAL", "Trimestral"),
                    ("SEMESTRAL", "Semestral"),
                    ("ANUAL", "Anual"),
                ],
                help_text=(
                    "Se vazio, usa a periodicidade do indicador. "
                    "Permite monitorar variáveis em ritmos diferentes."
                ),
                max_length=20,
                verbose_name="Periodicidade de monitoramento da variável",
            ),
        ),
    ]
