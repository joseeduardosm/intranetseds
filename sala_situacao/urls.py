"""
Roteamento HTTP do app `sala_situacao`.

Este módulo conecta URLs às views (CBVs e function views) que executam fluxos de
consulta, cadastro, monitoramento e operações auxiliares em AJAX/JSON.

Integração com o projeto:
- este arquivo é incluído em `intranet/urls.py` sob o prefixo
  `/sala-de-situacao/`;
- os nomes de rota (`name=...`) são usados em templates, redirects e `reverse()`.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Endpoints auxiliares (autocomplete/sugestões e APIs de suporte do frontend).
    path(
        "mock/plotly-cards/",
        views.SalaSituacaoPlotlyCardsMockView.as_view(),
        name="sala_plotly_cards_mock",
    ),
    path(
        "variaveis/sugestoes/",
        views.variavel_sugestoes_api,
        name="sala_variavel_sugestoes_api",
    ),
    path(
        "painel-consolidado/grafico-variaveis/",
        views.painel_consolidado_grafico_variaveis_api,
        name="sala_painel_consolidado_grafico_variaveis_api",
    ),
    path(
        "marcadores/sugestoes/",
        views.marcador_sugestoes_api,
        name="sala_marcador_sugestoes_api",
    ),
    path(
        "marcadores/criar/",
        views.marcador_criar_api,
        name="sala_marcador_criar_api",
    ),
    path(
        "marcadores/<int:pk>/cor/",
        views.marcador_cor_api,
        name="sala_marcador_cor_api",
    ),
    path(
        "marcadores/<int:pk>/excluir/",
        views.marcador_excluir_api,
        name="sala_marcador_excluir_api",
    ),
    path(
        "marcadores/<str:tipo>/<int:pk>/",
        views.item_marcadores_api,
        name="sala_item_marcadores_api",
    ),
    path(
        "marcadores/<str:tipo>/<int:pk>/vincular/",
        views.item_marcador_vincular_api,
        name="sala_item_marcador_vincular_api",
    ),
    path(
        "marcadores/<str:tipo>/<int:pk>/<int:marcador_id>/",
        views.item_marcador_desvincular_api,
        name="sala_item_marcador_desvincular_api",
    ),
    # Visões consolidadas do módulo (home e painel com filtros agregados).
    path("", views.SalaSituacaoHomeView.as_view(), name="sala_situacao_home"),
    path(
        "painel-consolidado/",
        views.SalaSituacaoConsolidadoView.as_view(),
        name="sala_painel_consolidado",
    ),
    path(
        "indicadores-estrategicos/<int:pk>/indicadores-taticos/",
        views.IndicadoresTaticosPorIndicadorEstrategicoView.as_view(),
        name="sala_fluxo_indicadores_taticos_por_ie",
    ),
    path(
        "indicadores-estrategicos/<int:pk>/processos/",
        views.ProcessosPorIndicadorTaticoView.as_view(),
        name="sala_fluxo_processos",
    ),
    path(
        "indicadores-taticos/<int:pk>/processos/",
        views.ProcessosPorIndicadorTaticoView.as_view(),
        name="sala_fluxo_processos_legacy",
    ),
    path(
        "processos/<int:pk>/entregas/",
        views.EntregasPorProcessoView.as_view(),
        name="sala_fluxo_entregas",
    ),
    # CRUD de indicadores estratégicos.
    path(
        "indicadores-estrategicos/",
        views.SalaSituacaoIndicadoresRedirectView.as_view(),
        name="sala_indicador_estrategico_list",
    ),
    path(
        "indicadores-estrategicos/novo/",
        views.IndicadorEstrategicoCreateView.as_view(),
        name="sala_indicador_estrategico_create",
    ),
    path(
        "indicadores-estrategicos/<int:pk>/",
        views.IndicadorEstrategicoDetailView.as_view(),
        name="sala_indicador_estrategico_detail",
    ),
    path(
        "indicadores-estrategicos/<int:pk>/editar/",
        views.IndicadorEstrategicoUpdateView.as_view(),
        name="sala_indicador_estrategico_update",
    ),
    path(
        "indicadores-estrategicos/<int:pk>/excluir/",
        views.IndicadorEstrategicoDeleteView.as_view(),
        name="sala_indicador_estrategico_delete",
    ),
    path(
        "indicadores/<str:tipo>/<int:pk>/variaveis/nova/",
        views.IndicadorVariavelCreateView.as_view(),
        name="sala_indicador_variavel_create",
    ),
    # CRUD de indicadores táticos.
    path(
        "indicadores-taticos/",
        views.SalaSituacaoIndicadoresRedirectView.as_view(),
        name="sala_indicador_tatico_list",
    ),
    path(
        "indicadores-taticos/novo/",
        views.IndicadorTaticoCreateView.as_view(),
        name="sala_indicador_tatico_create",
    ),
    path(
        "indicadores-taticos/<int:pk>/",
        views.IndicadorTaticoDetailView.as_view(),
        name="sala_indicador_tatico_detail",
    ),
    path(
        "indicadores-taticos/<int:pk>/editar/",
        views.IndicadorTaticoUpdateView.as_view(),
        name="sala_indicador_tatico_update",
    ),
    path(
        "indicadores-taticos/<int:pk>/excluir/",
        views.IndicadorTaticoDeleteView.as_view(),
        name="sala_indicador_tatico_delete",
    ),
    # CRUD de processos.
    path(
        "processos/",
        views.ProcessoListView.as_view(),
        name="sala_processo_list",
    ),
    path(
        "processos/novo/",
        views.ProcessoCreateView.as_view(),
        name="sala_processo_create",
    ),
    path(
        "processos/<int:pk>/",
        views.ProcessoDetailView.as_view(),
        name="sala_processo_detail",
    ),
    path(
        "processos/<int:pk>/editar/",
        views.ProcessoUpdateView.as_view(),
        name="sala_processo_update",
    ),
    path(
        "processos/<int:pk>/excluir/",
        views.ProcessoDeleteView.as_view(),
        name="sala_processo_delete",
    ),
    # CRUD e monitoramento de entregas.
    path(
        "entregas/",
        views.EntregaListView.as_view(),
        name="sala_entrega_list",
    ),
    path(
        "entregas/calendario/eventos/",
        views.entrega_calendario_api,
        name="sala_entrega_calendario_api",
    ),
    path(
        "entregas/nova/",
        views.EntregaCreateView.as_view(),
        name="sala_entrega_create",
    ),
    path(
        "entregas/<int:pk>/",
        views.EntregaDetailView.as_view(),
        name="sala_entrega_detail",
    ),
    path(
        "entregas/<int:pk>/editar/",
        views.EntregaUpdateView.as_view(),
        name="sala_entrega_update",
    ),
    path(
        "entregas/<int:pk>/monitorar/",
        views.entrega_monitorar,
        name="sala_entrega_monitorar",
    ),
    path(
        "entregas/<int:pk>/excluir/",
        views.EntregaDeleteView.as_view(),
        name="sala_entrega_delete",
    ),
]
