"""
Módulo de configuração do app `folha_ponto` dentro do ciclo de boot do Django.

Na arquitetura do framework, esta classe registra metadados do app para:
- descoberta em `INSTALLED_APPS`;
- resolução de labels de migração e permissões;
- integração com modelos, admin, URLs e templates vinculados ao app.
"""

from django.apps import AppConfig


class FolhaPontoConfig(AppConfig):
    """Define a identidade do app no projeto Django.

    Esta configuração é consumida internamente pelo Django para mapear:
    - nome técnico do app (`folha_ponto`);
    - tipo de chave primária padrão para modelos (`BigAutoField`).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "folha_ponto"
