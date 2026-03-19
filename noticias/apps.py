"""
Configuração do app `noticias` na arquitetura Django.

Este módulo declara a classe de configuração utilizada pelo Django para
registrar o app no `INSTALLED_APPS`. A partir dessa configuração, o framework
descobre modelos, admin, migrações, templates e URLs vinculadas ao app.
"""
from django.apps import AppConfig


class NoticiasConfig(AppConfig):
    """
    Define metadados básicos do app de notícias.

    Papel na arquitetura:
    - Identificar o app para o carregamento do Django.
    - Servir como ponto de extensão para inicializações futuras
      (ex.: registro de sinais no método `ready`, quando necessário).
    """
    name = 'noticias'
