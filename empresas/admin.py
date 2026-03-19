"""
Configuração do Django Admin para o app `empresas`.

Define colunas e campos de busca da entidade `Empresa` no painel admin.
"""

from django.contrib import admin

from .models import Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    """Customização da listagem administrativa de empresas."""

    list_display = ("nome", "cnpj")
    search_fields = ("nome", "cnpj")
