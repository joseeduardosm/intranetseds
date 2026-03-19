"""
Mapeamento de URLs do app `folha_ponto`.

Papel na arquitetura Django:
- conecta endpoints HTTP às views do app;
- separa fluxos de usuário comum (home/impressão) e fluxos administrativos de RH;
- serve de contrato público para navegação por templates e redirecionamentos.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.FolhaPontoHomeView.as_view(), name="folha_ponto_home"),
    path("brasao/", views.RHBrasaoView.as_view(), name="folha_ponto_brasao"),
    path("imprimir/", views.FolhaPontoPrintView.as_view(), name="folha_ponto_print"),
    path("feriados/", views.FeriadoListView.as_view(), name="folha_ponto_feriado_list"),
    path("feriados/novo/", views.FeriadoCreateView.as_view(), name="folha_ponto_feriado_create"),
    path("feriados/<int:pk>/editar/", views.FeriadoUpdateView.as_view(), name="folha_ponto_feriado_update"),
    path("feriados/<int:pk>/excluir/", views.FeriadoDeleteView.as_view(), name="folha_ponto_feriado_delete"),
    path("ferias/", views.FeriasListView.as_view(), name="folha_ponto_ferias_list"),
    path("ferias/novo/", views.FeriasCreateView.as_view(), name="folha_ponto_ferias_create"),
    path("ferias/<int:pk>/editar/", views.FeriasUpdateView.as_view(), name="folha_ponto_ferias_update"),
    path("ferias/<int:pk>/excluir/", views.FeriasDeleteView.as_view(), name="folha_ponto_ferias_delete"),
]
