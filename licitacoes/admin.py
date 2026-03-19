"""
Configuração do Django Admin para o app `licitacoes`.

Papel arquitetural:
- disponibiliza manutenção operacional dos modelos de TR;
- expõe filtros e ordenações para auditoria e correção manual de estrutura;
- integra diretamente com permissões padrão de modelos do Django.
"""

from django.contrib import admin

from .models import EtpTic, ItemSessao, SessaoTermo, SubsessaoTermo, TabelaItemLinha, TermoReferencia


@admin.register(TermoReferencia)
class TermoReferenciaAdmin(admin.ModelAdmin):
    """Admin de termos com foco em busca por apelido e processo SEI."""

    list_display = ("apelido", "processo_sei", "atualizado_em")
    search_fields = ("apelido", "processo_sei")


@admin.register(SessaoTermo)
class SessaoTermoAdmin(admin.ModelAdmin):
    """Admin de sessões de cada termo, com ordenação hierárquica."""

    list_display = ("termo", "ordem", "titulo")
    list_filter = ("termo",)
    ordering = ("termo", "ordem")


@admin.register(ItemSessao)
class ItemSessaoAdmin(admin.ModelAdmin):
    """Admin de itens e subitens com visão resumida de conteúdo textual."""

    list_display = ("sessao", "subsessao", "parent", "ordem", "texto_resumo")
    list_filter = ("sessao",)
    ordering = ("sessao", "parent", "ordem")

    def texto_resumo(self, obj):
        """Retorna prévia de até 80 caracteres para facilitar leitura em tabela."""

        return (obj.texto or "")[:80]


@admin.register(TabelaItemLinha)
class TabelaItemLinhaAdmin(admin.ModelAdmin):
    """Admin da planilha vinculada aos itens do termo."""

    list_display = (
        "item",
        "ordem",
        "catmat_catser",
        "siafisico",
        "unidade_fornecimento",
        "quantidade",
    )
    list_filter = ("item__sessao",)
    ordering = ("item", "ordem")


@admin.register(SubsessaoTermo)
class SubsessaoTermoAdmin(admin.ModelAdmin):
    """Admin de subseções associadas a sessões do TR."""

    list_display = ("sessao", "ordem", "titulo")
    list_filter = ("sessao",)
    ordering = ("sessao", "ordem")


@admin.register(EtpTic)
class EtpTicAdmin(admin.ModelAdmin):
    """Admin básico para manutenção de documentos ETP TIC."""

    list_display = ("numero_processo_servico", "titulo", "status", "secao_atual", "atualizado_em")
    search_fields = ("numero_processo_servico", "titulo")
    list_filter = ("status",)
