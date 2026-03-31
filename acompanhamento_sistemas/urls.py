from django.urls import path

from . import views


urlpatterns = [
    path("", views.SistemaListView.as_view(), name="acompanhamento_sistemas_list"),
    path("novo/", views.SistemaCreateView.as_view(), name="acompanhamento_sistemas_create"),
    path("<int:pk>/", views.SistemaDetailView.as_view(), name="acompanhamento_sistemas_detail"),
    path("<int:pk>/editar/", views.SistemaUpdateView.as_view(), name="acompanhamento_sistemas_update"),
    path("<int:pk>/excluir/", views.SistemaDeleteView.as_view(), name="acompanhamento_sistemas_delete"),
    path("entregas/<int:pk>/", views.EntregaSistemaDetailView.as_view(), name="acompanhamento_sistemas_entrega_detail"),
    path("entregas/<int:pk>/editar/", views.EntregaSistemaUpdateView.as_view(), name="acompanhamento_sistemas_entrega_update"),
    path("entregas/<int:pk>/excluir/", views.EntregaSistemaDeleteView.as_view(), name="acompanhamento_sistemas_entrega_delete"),
    path("etapas/<int:pk>/", views.EtapaSistemaDetailView.as_view(), name="acompanhamento_sistemas_etapa_detail"),
    path("etapas/<int:pk>/atualizar/", views.EtapaSistemaUpdateView.as_view(), name="acompanhamento_sistemas_etapa_update"),
    path("etapas/<int:pk>/nota/", views.EtapaSistemaNotaView.as_view(), name="acompanhamento_sistemas_etapa_nota"),
    path("<int:pk>/interessados/adicionar/", views.InteressadoSistemaCreateView.as_view(), name="acompanhamento_sistemas_interessado_add"),
    path("<int:pk>/interessados/<int:interessado_pk>/remover/", views.InteressadoSistemaDeleteView.as_view(), name="acompanhamento_sistemas_interessado_remove"),
    path("<int:pk>/entregas/nova/", views.EntregaSistemaCreateView.as_view(), name="acompanhamento_sistemas_entrega_create"),
]
