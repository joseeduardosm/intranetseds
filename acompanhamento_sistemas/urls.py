from django.urls import path

from . import views


urlpatterns = [
    path("", views.SistemaListView.as_view(), name="acompanhamento_sistemas_list"),
    path("mockups/processos/", views.MockProcessosView.as_view(), name="acompanhamento_sistemas_mock_processos"),
    path("mockups/processos/<slug:slug>/", views.MockProcessosView.as_view(), name="acompanhamento_sistemas_mock_processos_detail"),
    path("novo/", views.SistemaCreateView.as_view(), name="acompanhamento_sistemas_create"),
    path("<int:pk>/", views.SistemaDetailView.as_view(), name="acompanhamento_sistemas_detail"),
    path("<int:pk>/historico/", views.SistemaHistoricoView.as_view(), name="acompanhamento_sistemas_historico"),
    path("<int:pk>/processos/novo/", views.ProcessoRequisitoCreateView.as_view(), name="acompanhamento_sistemas_processo_create"),
    path("<int:pk>/nota/", views.SistemaNotaView.as_view(), name="acompanhamento_sistemas_nota"),
    path("<int:pk>/editar/", views.SistemaUpdateView.as_view(), name="acompanhamento_sistemas_update"),
    path("<int:pk>/excluir/", views.SistemaDeleteView.as_view(), name="acompanhamento_sistemas_delete"),
    path("processos/<int:pk>/", views.ProcessoRequisitoDetailView.as_view(), name="acompanhamento_sistemas_processo_detail"),
    path("processos/<int:pk>/editar/", views.ProcessoRequisitoUpdateView.as_view(), name="acompanhamento_sistemas_processo_update"),
    path("processos/<int:pk>/excluir/", views.ProcessoRequisitoDeleteView.as_view(), name="acompanhamento_sistemas_processo_delete"),
    path("processos/<int:pk>/transformar/", views.ProcessoRequisitoTransformarView.as_view(), name="acompanhamento_sistemas_processo_transformar"),
    path("processos/etapas/<int:pk>/", views.ProcessoRequisitoEtapaDetailView.as_view(), name="acompanhamento_sistemas_processo_etapa_detail"),
    path("processos/etapas/<int:pk>/atualizar/", views.ProcessoRequisitoEtapaUpdateView.as_view(), name="acompanhamento_sistemas_processo_etapa_update"),
    path("entregas/<int:pk>/", views.EntregaSistemaDetailView.as_view(), name="acompanhamento_sistemas_entrega_detail"),
    path("entregas/<int:pk>/historico/", views.EntregaSistemaHistoricoView.as_view(), name="acompanhamento_sistemas_entrega_historico"),
    path("entregas/<int:pk>/editar/", views.EntregaSistemaUpdateView.as_view(), name="acompanhamento_sistemas_entrega_update"),
    path("entregas/<int:pk>/publicar/", views.EntregaSistemaPublishView.as_view(), name="acompanhamento_sistemas_entrega_publish"),
    path("entregas/<int:pk>/excluir/", views.EntregaSistemaDeleteView.as_view(), name="acompanhamento_sistemas_entrega_delete"),
    path("etapas/calendario/", views.EtapaSistemaCalendarioView.as_view(), name="acompanhamento_sistemas_etapa_calendario"),
    path("etapas/<int:pk>/", views.EtapaSistemaDetailView.as_view(), name="acompanhamento_sistemas_etapa_detail"),
    path("etapas/<int:pk>/atualizar/", views.EtapaSistemaUpdateView.as_view(), name="acompanhamento_sistemas_etapa_update"),
    path("etapas/<int:pk>/nota/", views.EtapaSistemaNotaView.as_view(), name="acompanhamento_sistemas_etapa_nota"),
    path("<int:pk>/interessados/adicionar/", views.InteressadoSistemaCreateView.as_view(), name="acompanhamento_sistemas_interessado_add"),
    path("<int:pk>/interessados/<int:interessado_pk>/remover/", views.InteressadoSistemaDeleteView.as_view(), name="acompanhamento_sistemas_interessado_remove"),
    path("<int:pk>/entregas/nova/", views.EntregaSistemaCreateView.as_view(), name="acompanhamento_sistemas_entrega_create"),
]
