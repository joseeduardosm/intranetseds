"""
Mapeamento de rotas HTTP do app `lousa_digital`.

Este arquivo conecta endpoints às views que controlam:
- listagem e ciclo de vida de processos;
- criação/devolução de encaminhamentos;
- registro de notas na timeline.
"""

from django.urls import path

from . import views


urlpatterns = [
    path("", views.ProcessoListView.as_view(), name="lousa_digital_list"),
    path("dashboard/", views.ProcessoDashboardView.as_view(), name="lousa_digital_dashboard"),
    path("novo/", views.ProcessoCreateView.as_view(), name="lousa_digital_create"),
    path("<int:pk>/", views.ProcessoDetailView.as_view(), name="lousa_digital_detail"),
    path("<int:pk>/editar/", views.ProcessoUpdateView.as_view(), name="lousa_digital_update"),
    path("<int:pk>/excluir/", views.ProcessoDeleteView.as_view(), name="lousa_digital_delete"),
    path("<int:pk>/encaminhar/", views.CriarEncaminhamentoView.as_view(), name="lousa_digital_encaminhar"),
    path(
        "<int:pk>/encaminhamentos/<int:encaminhamento_id>/devolver/",
        views.DevolverEncaminhamentoView.as_view(),
        name="lousa_digital_devolver",
    ),
    path("<int:pk>/nota/", views.CriarNotaView.as_view(), name="lousa_digital_nota"),
]
