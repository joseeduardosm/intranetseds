"""
Configuração de aplicação Django para o app `sala_situacao`.

Este arquivo registra o app no Django App Registry e define metadados usados
durante carregamento de modelos, migrações, permissões e exibição no admin.
"""

from django.apps import AppConfig


class SalaSituacaoConfig(AppConfig):
    """
    Classe de configuração principal do módulo Sala de Situação.

    Papel na arquitetura:
    - identifica o pacote Python do app (`name`);
    - define tipo padrão de chave primária para novos modelos;
    - fornece metadados consumidos pelo ecossistema Django.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sala_situacao'
