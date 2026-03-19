from django.urls import path

from . import views


urlpatterns = [
    path("", views.MonitoramentoHomeView.as_view(), name="monitoramento_home"),
    path("projetos/novo/", views.ProjetoMonitoramentoCreateView.as_view(), name="monitoramento_projeto_create"),
    path("projetos/<int:pk>/", views.ProjetoMonitoramentoDetailView.as_view(), name="monitoramento_projeto_detail"),
    path("projetos/<int:pk>/conexao/", views.ConexaoMonitoramentoUpdateView.as_view(), name="monitoramento_conexao"),
    path("projetos/<int:pk>/esquema/", views.EsquemaMonitoramentoView.as_view(), name="monitoramento_esquema"),
    path("projetos/<int:pk>/dashboards/", views.DashboardProjetoListView.as_view(), name="monitoramento_dashboard_list"),
    path("projetos/<int:pk>/dashboards/novo/", views.DashboardMonitoramentoCreateView.as_view(), name="monitoramento_dashboard_create"),
    path("dashboards/<int:pk>/", views.DashboardMonitoramentoDetailView.as_view(), name="monitoramento_dashboard_detail"),
    path("dashboards/<int:pk>/editar/", views.DashboardMonitoramentoUpdateView.as_view(), name="monitoramento_dashboard_update"),
    path("dashboards/<int:pk>/excluir/", views.DashboardMonitoramentoDeleteView.as_view(), name="monitoramento_dashboard_delete"),
    path("graficos/<int:pk>/exportar/", views.exportar_grafico_monitoramento, name="monitoramento_grafico_exportar"),
]
