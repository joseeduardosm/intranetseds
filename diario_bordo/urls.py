"""
Roteamento HTTP do app `diario_bordo`.

Mapeia URLs para fluxos de listagem, relatório, detalhe e CRUD de blocos
e incrementos, além da ação de ciência de incremento.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Visão principal (cards/tabela) dos blocos.
    path("", views.BlocoTrabalhoListView.as_view(), name="diario_bordo_list"),
    # API para alteração rápida de status no board Kanban.
    path("<int:pk>/status/", views.bloco_status_api, name="diario_bordo_bloco_status_api"),
    # Relatórios com filtros de status/legenda/tipo.
    path("relatorio/", views.BlocoTrabalhoRelatorioView.as_view(), name="diario_bordo_relatorio"),
    path(
        "relatorio/<int:pk>/",
        views.BlocoTrabalhoRelatorioDetalheView.as_view(),
        name="diario_bordo_relatorio_detalhe",
    ),
    # CRUD de blocos.
    path("novo/", views.BlocoTrabalhoCreateView.as_view(), name="diario_bordo_create"),
    path("<int:pk>/", views.BlocoTrabalhoDetailView.as_view(), name="diario_bordo_detail"),
    path("<int:pk>/editar/", views.BlocoTrabalhoUpdateView.as_view(), name="diario_bordo_update"),
    path("<int:pk>/excluir/", views.BlocoTrabalhoDeleteView.as_view(), name="diario_bordo_delete"),
    # CRUD e ações de incrementos.
    path("<int:pk>/incrementos/novo/", views.IncrementoCreateView.as_view(), name="diario_bordo_incremento_create"),
    path("incrementos/<int:pk>/ciente/", views.incremento_ciente, name="diario_bordo_incremento_ciente"),
    path("incrementos/<int:pk>/lido/", views.incremento_marcar_lido, name="diario_bordo_incremento_marcar_lido"),
    path("incrementos/<int:pk>/editar/", views.IncrementoUpdateView.as_view(), name="diario_bordo_incremento_update"),
    path("incrementos/<int:pk>/excluir/", views.IncrementoDeleteView.as_view(), name="diario_bordo_incremento_delete"),
    # Marcadores próprios do Diário.
    path("marcadores/sugestoes/", views.marcador_sugestoes_api, name="diario_bordo_marcador_sugestoes_api"),
    path("marcadores/criar/", views.marcador_criar_api, name="diario_bordo_marcador_criar_api"),
    path("marcadores/<int:pk>/cor/", views.marcador_cor_api, name="diario_bordo_marcador_cor_api"),
    path("marcadores/<int:pk>/excluir/", views.marcador_excluir_api, name="diario_bordo_marcador_excluir_api"),
    path("blocos/<int:pk>/marcadores/", views.bloco_marcadores_api, name="diario_bordo_bloco_marcadores_api"),
    path("blocos/<int:pk>/marcadores/vincular/", views.bloco_marcador_vincular_api, name="diario_bordo_bloco_marcador_vincular_api"),
    path("blocos/<int:pk>/marcadores/<int:marcador_id>/", views.bloco_marcador_desvincular_api, name="diario_bordo_bloco_marcador_desvincular_api"),
]
