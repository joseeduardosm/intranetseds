"""
Roteamento HTTP do app `administracao`.

Este arquivo define as URLs publicas do modulo e as associa as views
responsaveis por cada fluxo: configuracoes, RH, RF/changelog, AD e CRUD
de atalhos. Ele integra a camada de apresentacao com regras de permissao
encapsuladas nas views.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Hub principal de configuracoes administrativas.
    path("configuracoes/", views.ConfiguracoesView.as_view(), name="administracao_configuracoes"),
    # Tela de gestao de RFs/changelog e markdowns em docs/.
    path("rfs/", views.RFChangelogView.as_view(), name="administracao_rfs"),
    # Atalho para funcionalidades de RH com controle de permissao dedicado.
    path("rh/", views.RHView.as_view(), name="administracao_rh"),
    # Configuracao de Active Directory (somente superusuario).
    path(
        "configuracoes/ad/",
        views.ADConfigView.as_view(),
        name="administracao_ad_config",
    ),
    path(
        "configuracoes/smtp/",
        views.SMTPConfigView.as_view(),
        name="administracao_smtp_config",
    ),
    path(
        "configuracoes/identidade-visual/",
        views.IdentidadeVisualConfigView.as_view(),
        name="administracao_identidade_visual",
    ),
    path(
        "configuracoes/backup-sistema/",
        views.SystemBackupDownloadView.as_view(),
        name="administracao_backup_sistema",
    ),
    # CRUD de atalhos de servico exibidos na interface.
    path(
        "atalhos/",
        views.AtalhoServicoListView.as_view(),
        name="administracao_atalho_list",
    ),
    path(
        "atalhos/novo/",
        views.AtalhoServicoCreateView.as_view(),
        name="administracao_atalho_create",
    ),
    path(
        "atalhos/<int:pk>/editar/",
        views.AtalhoServicoUpdateView.as_view(),
        name="administracao_atalho_update",
    ),
    path(
        "atalhos/<int:pk>/excluir/",
        views.AtalhoServicoDeleteView.as_view(),
        name="administracao_atalho_delete",
    ),
    path(
        "atalhos-administracao/",
        views.AtalhoAdministracaoListView.as_view(),
        name="administracao_atalho_administracao_list",
    ),
    path(
        "atalhos-administracao/novo/",
        views.AtalhoAdministracaoCreateView.as_view(),
        name="administracao_atalho_administracao_create",
    ),
    path(
        "atalhos-administracao/<int:pk>/editar/",
        views.AtalhoAdministracaoUpdateView.as_view(),
        name="administracao_atalho_administracao_update",
    ),
    path(
        "atalhos-administracao/<int:pk>/excluir/",
        views.AtalhoAdministracaoDeleteView.as_view(),
        name="administracao_atalho_administracao_delete",
    ),
]
