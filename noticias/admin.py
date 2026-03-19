"""
Configuração do Django Admin para o app `noticias`.

Este módulo integra o model `Noticia` ao painel administrativo nativo do
Django, permitindo que equipes autorizadas façam CRUD de conteúdo com filtros
e busca textual sem criar uma interface customizada no front-end.
"""
from django.contrib import admin

from .models import Noticia


@admin.register(Noticia)
class NoticiaAdmin(admin.ModelAdmin):
    """
    Personaliza a experiência de gestão de notícias no Django Admin.

    Papel na arquitetura:
    - Define colunas, filtros e campos pesquisáveis para operações de backoffice.
    - Reduz custo operacional de manutenção de conteúdo institucional.
    """
    # Campos exibidos na listagem.
    list_display = ('titulo', 'categoria', 'data_publicacao')
    # Filtros laterais úteis para o admin.
    list_filter = ('categoria', 'data_publicacao')
    # Campos pesquisáveis.
    search_fields = ('titulo', 'texto')
