"""
Configuração do Django Admin para o app `prepostos`.

Este módulo registra o model `Preposto` no admin e define parâmetros de
listagem, busca e filtros para facilitar operações administrativas.
"""
from django.contrib import admin

from .models import Preposto


@admin.register(Preposto)
class PrepostoAdmin(admin.ModelAdmin):
    """
    Personaliza a administração de prepostos no painel Django.

    Papel arquitetural:
    - Expor informações chave em listagem para operação rápida.
    - Permitir busca textual e filtros por empresa.
    """
    # Colunas exibidas na listagem principal do admin.
    list_display = ("nome", "cpf", "empresa", "telefone", "email")
    # Campos indexados para pesquisa textual no admin.
    search_fields = ("nome", "cpf", "empresa__nome")
    # Filtros laterais para refino da consulta administrativa.
    list_filter = ("empresa",)
