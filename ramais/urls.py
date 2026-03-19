"""
Mapa de URLs do app `ramais`.

Este módulo conecta endpoints HTTP às views do diretório de ramais e do
organograma. É incluído no roteador principal do projeto sob o prefixo
`/ramais/`.
"""
from django.urls import path

from . import views

# Rotas do app de ramais.
urlpatterns = [
    # Lista e busca de ramais.
    path('', views.PessoaRamalListView.as_view(), name='ramais_list'),
    # Organograma hierárquico.
    path('organograma/', views.OrganogramaView.as_view(), name='organograma'),
    # CRUD de ramais (somente staff nas views).
    path('novo/', views.PessoaRamalCreateView.as_view(), name='ramais_create'),
    path('<int:pk>/', views.PessoaRamalDetailView.as_view(), name='ramais_detail'),
    path('<int:pk>/editar/', views.PessoaRamalUpdateView.as_view(), name='ramais_update'),
    path('<int:pk>/excluir/', views.PessoaRamalDeleteView.as_view(), name='ramais_delete'),
]
