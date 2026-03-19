"""
Configuração de inicialização do app `contratos`.

Este arquivo registra o app no ciclo de boot do Django para que modelos,
views, formulários, templates e migrações sejam descobertos pelo framework.
"""

from django.apps import AppConfig


class ContratosConfig(AppConfig):
    """
    Classe de configuração do app na arquitetura Django.

    Papel:
    - declarar o nome técnico do módulo em `INSTALLED_APPS`;
    - permitir carregamento dos componentes do app pelo Django.
    """

    name = 'contratos'
