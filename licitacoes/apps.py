"""
Configuração de bootstrap do app `licitacoes` no ciclo de inicialização do Django.

Integração na arquitetura:
- registra o app em `INSTALLED_APPS`;
- define metadados usados por migrações, permissões e interface administrativa;
- conecta os módulos internos (`models`, `views`, `forms`, `admin`) ao runtime.
"""

from django.apps import AppConfig


class LicitacoesConfig(AppConfig):
    """Representa a identidade do módulo de licitações dentro do projeto Django.

    Papel arquitetural:
    - define nome técnico do app;
    - estabelece tipo padrão de chave primária para novos modelos.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "licitacoes"
    verbose_name = "Licitacoes"
