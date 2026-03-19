"""
Roteamento HTTP do app `empresas`.

Mapeia endpoints de CRUD para as views do módulo, mantendo uma convenção
simples de navegação para cadastro e manutenção de empresas.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Listagem principal de empresas.
    path("", views.EmpresaListView.as_view(), name="empresas_list"),
    # Criação de nova empresa.
    path("novo/", views.EmpresaCreateView.as_view(), name="empresas_create"),
    # Detalhe de empresa por PK.
    path("<int:pk>/", views.EmpresaDetailView.as_view(), name="empresas_detail"),
    # Atualização de empresa existente.
    path("<int:pk>/editar/", views.EmpresaUpdateView.as_view(), name="empresas_update"),
    # Exclusão de empresa.
    path("<int:pk>/excluir/", views.EmpresaDeleteView.as_view(), name="empresas_delete"),
]
