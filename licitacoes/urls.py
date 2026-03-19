"""
Contrato de roteamento HTTP do app `licitacoes`.

Integração com o restante do módulo:
- cada rota mapeia para uma view responsável por uma etapa do fluxo de TR;
- os nomes (`name=...`) são usados por templates e redirecionamentos internos;
- os parâmetros de URL (`pk`, `sessao_pk`, `item_pk`) definem escopo do recurso.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.LicitacoesHomeView.as_view(), name="licitacoes_home"),
    path("etp-tic/", views.EtpTicListView.as_view(), name="licitacoes_etp_tic_list"),
    path("etp-tic/novo/", views.EtpTicCreateView.as_view(), name="licitacoes_etp_tic_create"),
    path("etp-tic/<int:pk>/editar/", views.EtpTicEditView.as_view(), name="licitacoes_etp_tic_edit"),
    path("etp-tic/<int:pk>/autosave/", views.EtpTicAutosaveView.as_view(), name="licitacoes_etp_tic_autosave"),
    path("etp-tic/<int:pk>/preview/", views.EtpTicPreviewView.as_view(), name="licitacoes_etp_tic_preview"),
    path("etp-tic/<int:pk>/exportar-docx/", views.EtpTicExportDocxView.as_view(), name="licitacoes_etp_tic_export_docx"),
    path("etp-tic/<int:pk>/concluir/", views.EtpTicConcluirView.as_view(), name="licitacoes_etp_tic_concluir"),
    path("etp-tic/<int:pk>/excluir/", views.EtpTicDeleteView.as_view(), name="licitacoes_etp_tic_delete"),
    path("termos/", views.TermoReferenciaListView.as_view(), name="licitacoes_termo_list"),
    path("termos/novo/", views.TermoReferenciaCreateView.as_view(), name="licitacoes_termo_create"),
    path("termos/importar/", views.TermoReferenciaImportarView.as_view(), name="licitacoes_termo_import"),
    path("termos/<int:pk>/", views.TermoReferenciaDetailView.as_view(), name="licitacoes_termo_detail"),
    path("termos/<int:pk>/exportar-docx/", views.TermoReferenciaExportDocxView.as_view(), name="licitacoes_termo_export_docx"),
    path("termos/<int:pk>/editar/", views.TermoReferenciaUpdateView.as_view(), name="licitacoes_termo_update"),
    path("termos/<int:pk>/excluir/", views.TermoReferenciaDeleteView.as_view(), name="licitacoes_termo_delete"),
    path("termos/<int:pk>/duplicar/", views.TermoReferenciaDuplicarView.as_view(), name="licitacoes_termo_duplicate"),
    path(
        "termos/<int:termo_pk>/sessoes/nova/",
        views.SessaoTermoCreateView.as_view(),
        name="licitacoes_sessao_create",
    ),
    path(
        "termos/<int:termo_pk>/sessoes/<int:pk>/editar/",
        views.SessaoTermoUpdateView.as_view(),
        name="licitacoes_sessao_update",
    ),
    path(
        "termos/<int:termo_pk>/sessoes/<int:pk>/excluir/",
        views.SessaoTermoDeleteView.as_view(),
        name="licitacoes_sessao_delete",
    ),
    path(
        "termos/<int:termo_pk>/sessoes/<int:pk>/subir/",
        views.SessaoMoveUpView.as_view(),
        name="licitacoes_sessao_up",
    ),
    path(
        "termos/<int:termo_pk>/sessoes/<int:pk>/descer/",
        views.SessaoMoveDownView.as_view(),
        name="licitacoes_sessao_down",
    ),
    path(
        "sessoes/<int:sessao_pk>/subsessoes/nova/",
        views.SubsessaoTermoCreateView.as_view(),
        name="licitacoes_subsessao_create",
    ),
    path(
        "sessoes/<int:sessao_pk>/subsessoes/<int:pk>/editar/",
        views.SubsessaoTermoUpdateView.as_view(),
        name="licitacoes_subsessao_update",
    ),
    path(
        "sessoes/<int:sessao_pk>/subsessoes/<int:pk>/excluir/",
        views.SubsessaoTermoDeleteView.as_view(),
        name="licitacoes_subsessao_delete",
    ),
    path(
        "sessoes/<int:sessao_pk>/subsessoes/<int:pk>/subir/",
        views.SubsessaoMoveUpView.as_view(),
        name="licitacoes_subsessao_up",
    ),
    path(
        "sessoes/<int:sessao_pk>/subsessoes/<int:pk>/descer/",
        views.SubsessaoMoveDownView.as_view(),
        name="licitacoes_subsessao_down",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/novo/",
        views.ItemSessaoCreateView.as_view(),
        name="licitacoes_item_create",
    ),
    path(
        "sessoes/<int:sessao_pk>/subsessoes/<int:subsessao_pk>/itens/novo/",
        views.ItemSessaoCreateView.as_view(),
        name="licitacoes_item_create_in_subsessao",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:parent_pk>/subitem/novo/",
        views.ItemSessaoCreateView.as_view(),
        name="licitacoes_item_subitem_create",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:pk>/editar/",
        views.ItemSessaoUpdateView.as_view(),
        name="licitacoes_item_update",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:pk>/excluir/",
        views.ItemSessaoDeleteView.as_view(),
        name="licitacoes_item_delete",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:pk>/subir/",
        views.ItemMoveUpView.as_view(),
        name="licitacoes_item_up",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:pk>/descer/",
        views.ItemMoveDownView.as_view(),
        name="licitacoes_item_down",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:item_pk>/tabela/novo/",
        views.TabelaItemLinhaCreateView.as_view(),
        name="licitacoes_tabela_item_create",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:item_pk>/tabela/<int:pk>/editar/",
        views.TabelaItemLinhaUpdateView.as_view(),
        name="licitacoes_tabela_item_update",
    ),
    path(
        "sessoes/<int:sessao_pk>/itens/<int:item_pk>/tabela/<int:pk>/excluir/",
        views.TabelaItemLinhaDeleteView.as_view(),
        name="licitacoes_tabela_item_delete",
    ),
]
