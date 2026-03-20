from django.urls import path

from . import views

urlpatterns = [
    path("", views.SalaSituacaoV2HomeView.as_view(), name="sala_situacao_home"),
    path("indicadores/", views.IndicadorListView.as_view(), name="sala_indicador_estrategico_list"),
    path("indicadores/novo/", views.IndicadorCreateView.as_view(), name="sala_indicador_estrategico_create"),
    path("indicadores/<int:pk>/", views.IndicadorDetailView.as_view(), name="sala_indicador_estrategico_detail"),
    path("indicadores/<int:pk>/editar/", views.IndicadorUpdateView.as_view(), name="sala_indicador_estrategico_update"),
    path("indicadores/<int:pk>/excluir/", views.IndicadorDeleteView.as_view(), name="sala_indicador_estrategico_delete"),
    # Alias legados para manter compatibilidade de reverse.
    path("indicadores-taticos/", views.IndicadorListView.as_view(), name="sala_indicador_tatico_list"),
    path("indicadores-taticos/novo/", views.IndicadorCreateView.as_view(), name="sala_indicador_tatico_create"),
    path("indicadores-taticos/<int:pk>/", views.IndicadorDetailView.as_view(), name="sala_indicador_tatico_detail"),
    path("indicadores-taticos/<int:pk>/editar/", views.IndicadorUpdateView.as_view(), name="sala_indicador_tatico_update"),
    path("indicadores-taticos/<int:pk>/excluir/", views.IndicadorDeleteView.as_view(), name="sala_indicador_tatico_delete"),
    path("processos/", views.ProcessoListView.as_view(), name="sala_processo_list"),
    path("processos/novo/", views.ProcessoCreateView.as_view(), name="sala_processo_create"),
    path("processos/<int:pk>/", views.ProcessoDetailView.as_view(), name="sala_processo_detail"),
    path("processos/<int:pk>/editar/", views.ProcessoUpdateView.as_view(), name="sala_processo_update"),
    path("processos/<int:pk>/excluir/", views.ProcessoDeleteView.as_view(), name="sala_processo_delete"),
    path("entregas/", views.EntregaListView.as_view(), name="sala_entrega_list"),
    path("entregas/calendario/eventos/", views.entrega_calendario_api, name="sala_entrega_calendario_api"),
    path("entregas/nova/", views.EntregaCreateView.as_view(), name="sala_entrega_create"),
    path("entregas/<int:pk>/", views.EntregaDetailView.as_view(), name="sala_entrega_detail"),
    path("entregas/<int:pk>/editar/", views.EntregaUpdateView.as_view(), name="sala_entrega_update"),
    path("entregas/<int:pk>/excluir/", views.EntregaDeleteView.as_view(), name="sala_entrega_delete"),
    path("entregas/<int:pk>/monitorar/", views.EntregaMonitorarView.as_view(), name="sala_entrega_monitorar"),
]
