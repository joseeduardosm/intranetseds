"""
Mapa de rotas do app `reserva_salas`.

Este arquivo define os endpoints locais do app e os conecta às views baseadas
em classe (`views.py`). O projeto principal inclui estas rotas sob o prefixo
`/reserva-salas/` em `intranet/urls.py`.

Integração na arquitetura:
- URLs nomeadas (`name=...`) são usadas em templates, `reverse()` e
  `get_absolute_url()` dos modelos.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.SalaListView.as_view(), name="salas_list"),
    path("dashboard/", views.ReservaDashboardView.as_view(), name="reservas_dashboard"),
    path("dashboard/exportar/", views.reservas_dashboard_exportar, name="reservas_dashboard_exportar"),
    path("nova/", views.SalaCreateView.as_view(), name="salas_create"),
    path("<int:pk>/", views.SalaDetailView.as_view(), name="salas_detail"),
    path("<int:pk>/editar/", views.SalaUpdateView.as_view(), name="salas_update"),
    path("<int:pk>/excluir/", views.SalaDeleteView.as_view(), name="salas_delete"),
    path("reservas/", views.ReservaListView.as_view(), name="reservas_list"),
    path("reservas/nova/", views.ReservaCreateView.as_view(), name="reservas_create"),
    path("reservas/<int:pk>/", views.ReservaDetailView.as_view(), name="reservas_detail"),
    path("reservas/<int:pk>/editar/", views.ReservaUpdateView.as_view(), name="reservas_update"),
    path("reservas/<int:pk>/excluir/", views.ReservaDeleteView.as_view(), name="reservas_delete"),
]
