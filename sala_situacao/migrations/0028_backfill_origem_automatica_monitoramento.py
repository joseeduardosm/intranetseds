"""
Migração de banco: registra mudanças estruturais/evolutivas no schema e dados.

Leitura recomendada para iniciantes: comece pelos itens públicos deste arquivo,
siga para dependências chamadas e confira os testes para observar cenários reais.
"""

from django.db import migrations


def marcar_processos_monitoramento_automatico(apps, schema_editor):
    """Função `marcar_processos_monitoramento_automatico` com finalidade específica no fluxo do app.

    Explicação pedagógica:
    - Executa uma etapa de negócio/infraestrutura dentro de `sala_situacao`.
    - O retorno e os efeitos colaterais devem ser lidos junto com chamadas no código.
    - Parâmetros recebidos: `apps`, `schema_editor`.
    """

    Processo = apps.get_model("sala_situacao", "Processo")
    (
        Processo.objects.filter(
            nome__startswith='Monitoramento de "',
            nome__contains='" do indicador "',
            origem_automatica_monitoramento=False,
        ).update(origem_automatica_monitoramento=True)
    )


def noop_reverse(apps, schema_editor):
    """Função `noop_reverse` com finalidade específica no fluxo do app.

    Explicação pedagógica:
    - Executa uma etapa de negócio/infraestrutura dentro de `sala_situacao`.
    - O retorno e os efeitos colaterais devem ser lidos junto com chamadas no código.
    - Parâmetros recebidos: `apps`, `schema_editor`.
    """

    return


class Migration(migrations.Migration):

    """Representa a estrutura `Migration` no app `sala_situacao`.

    Esta classe concentra regras e comportamentos relacionados ao domínio
    de monitoramento/gestão do painel. Para auditoria, leia os métodos na
    ordem para entender como os dados entram, são validados e persistidos.
    """

    dependencies = [
        ("sala_situacao", "0027_indicadorestrategico_criado_por_and_more"),
    ]

    operations = [
        migrations.RunPython(marcar_processos_monitoramento_automatico, noop_reverse),
    ]
