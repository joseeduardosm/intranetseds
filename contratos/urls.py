"""
Roteamento HTTP do app `contratos`.

Este arquivo mapeia URLs para views de CRUD de contratos, conectando
a camada de navegação aos fluxos de negócio implementados em `views.py`.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Listagem principal com visão de prazos.
    path("", views.ContratoListView.as_view(), name="contratos_list"),
    # Criação de novo contrato.
    path("novo/", views.ContratoCreateView.as_view(), name="contratos_create"),
    # Detalhamento de contrato por identificador.
    path("<int:pk>/", views.ContratoDetailView.as_view(), name="contratos_detail"),
    # Edição de contrato existente.
    path("<int:pk>/editar/", views.ContratoUpdateView.as_view(), name="contratos_update"),
    # Exclusão com confirmação.
    path("<int:pk>/excluir/", views.ContratoDeleteView.as_view(), name="contratos_delete"),
]
