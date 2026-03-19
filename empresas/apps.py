"""
Configuração de inicialização do app `empresas`.

Este arquivo registra o app no ciclo de boot do Django, permitindo
descoberta de modelos, views, URLs, templates e migrações do módulo.
"""

from django.apps import AppConfig


class EmpresasConfig(AppConfig):
    """
    Classe de configuração do app na arquitetura Django.

    Papel:
    - declarar o nome técnico do app para integração com `INSTALLED_APPS`.
    """

    name = 'empresas'
