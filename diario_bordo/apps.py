"""
Configuração de inicialização do app `diario_bordo`.

Este arquivo registra o app no ecossistema Django para descoberta de
modelos, views, formulários, templates e migrações.
"""

from django.apps import AppConfig


class DiarioBordoConfig(AppConfig):
    """
    Classe de configuração do app na arquitetura Django.

    Papel:
    - definir o nome técnico do módulo usado em `INSTALLED_APPS`;
    - habilitar o carregamento dos componentes do app em runtime.
    """

    name = 'diario_bordo'
