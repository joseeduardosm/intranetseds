"""
Mapa de rotas do app `prepostos`.

Este módulo conecta URLs às views baseadas em classe do app e é incluído em
`intranet/urls.py` no prefixo `/prepostos/`.
"""
from django.urls import path

from . import views

urlpatterns = [
    # Lista de prepostos cadastrados.
    path("", views.PrepostoListView.as_view(), name="prepostos_list"),
    # Cadastro de novo preposto.
    path("novo/", views.PrepostoCreateView.as_view(), name="prepostos_create"),
    # Detalhe de um preposto por identificador.
    path("<int:pk>/", views.PrepostoDetailView.as_view(), name="prepostos_detail"),
    # Edição de um preposto existente.
    path("<int:pk>/editar/", views.PrepostoUpdateView.as_view(), name="prepostos_update"),
    # Exclusão de um preposto existente.
    path("<int:pk>/excluir/", views.PrepostoDeleteView.as_view(), name="prepostos_delete"),
]
