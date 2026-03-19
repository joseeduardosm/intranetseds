"""
Migração de banco: registra mudanças estruturais/evolutivas no schema e dados.

Leitura recomendada para iniciantes: comece pelos itens públicos deste arquivo,
siga para dependências chamadas e confira os testes para observar cenários reais.
"""

from django.db import migrations


def normalizar_nomes_processos_monitoramento(apps, schema_editor):
    """Função `normalizar_nomes_processos_monitoramento` com finalidade específica no fluxo do app.

    Explicação pedagógica:
    - Executa uma etapa de negócio/infraestrutura dentro de `sala_situacao`.
    - O retorno e os efeitos colaterais devem ser lidos junto com chamadas no código.
    - Parâmetros recebidos: `apps`, `schema_editor`.
    """

    Processo = apps.get_model("sala_situacao", "Processo")
    for processo in Processo.objects.filter(nome__contains='do indicador ').iterator():
        nome = (processo.nome or "").replace('do indicador estratégico "', 'do indicador "')
        nome = nome.replace('do indicador tático "', 'do indicador "')
        if nome != processo.nome:
            processo.nome = nome
            processo.save(update_fields=["nome", "atualizado_em"])


class Migration(migrations.Migration):

    """Representa a estrutura `Migration` no app `sala_situacao`.

    Esta classe concentra regras e comportamentos relacionados ao domínio
    de monitoramento/gestão do painel. Para auditoria, leia os métodos na
    ordem para entender como os dados entram, são validados e persistidos.
    """

    dependencies = [
        ("sala_situacao", "0024_entrega_periodo_fim_entrega_periodo_inicio_and_more"),
    ]

    operations = [
        migrations.RunPython(normalizar_nomes_processos_monitoramento, migrations.RunPython.noop),
    ]
