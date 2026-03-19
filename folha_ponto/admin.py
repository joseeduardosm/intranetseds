"""
Configuração do Django Admin para o app `folha_ponto`.

Integração arquitetural:
- publica no painel administrativo os modelos de apoio à folha ponto;
- facilita operação diária de RH sem necessidade de acesso direto ao banco;
- usa os modelos definidos em `models.py` e respeita permissões do Django auth.
"""

from django.contrib import admin

from .models import ConfiguracaoRH, Feriado, FeriasServidor


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    """Customiza listagem de feriados no admin para operação de calendário."""

    list_display = ("data", "descricao")
    search_fields = ("descricao",)
    ordering = ("data",)


@admin.register(FeriasServidor)
class FeriasServidorAdmin(admin.ModelAdmin):
    """Customiza gestão de períodos de férias vinculados a servidores."""

    list_display = ("servidor", "data_inicio", "data_fim", "criado_por")
    list_filter = ("data_inicio", "data_fim")
    search_fields = ("servidor__nome", "servidor__usuario__first_name", "servidor__usuario__username")


@admin.register(ConfiguracaoRH)
class ConfiguracaoRHAdmin(admin.ModelAdmin):
    """Exibe configuração global de RH (especialmente o brasão institucional)."""

    list_display = ("id", "atualizado_em")
