"""
Tabela de rotas HTTP do app `noticias`.

Integração na arquitetura Django:
- Mapeia URLs para views baseadas em classe (CBVs) do app.
- É incluído em `intranet/urls.py`, onde o app de notícias está montado na raiz.
- Define os endpoints de leitura pública e de CRUD com controle por permissão.
"""
from django.urls import path

from . import views

# Rotas do app de notícias.
urlpatterns = [
    # Listagem administrativa de notícias.
    path('', views.NoticiaListView.as_view(), name='noticia_list'),
    # Fluxos de manutenção de notícia (com checagem de permissões nas views).
    path('nova/', views.NoticiaCreateView.as_view(), name='noticia_create'),
    path('<int:pk>/', views.NoticiaDetailView.as_view(), name='noticia_detail'),
    path('<int:pk>/editar/', views.NoticiaUpdateView.as_view(), name='noticia_update'),
    path('<int:pk>/excluir/', views.NoticiaDeleteView.as_view(), name='noticia_delete'),
]
