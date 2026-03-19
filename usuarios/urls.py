"""
Roteamento do app `usuarios`.

Este módulo expõe endpoints de gestão de usuários e grupos baseados em views
class-based do Django. O projeto principal inclui essas rotas sob o prefixo
`/usuarios/` em `intranet/urls.py`.

Integração na arquitetura:
- nomes de rota são usados por templates, `reverse()` e redirects das views.
"""

from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    # CRUD de usuários.
    path("", views.UsuarioListView.as_view(), name="usuarios_list"),
    path("novo/", views.UsuarioCreateView.as_view(), name="usuarios_create"),
    path("<int:pk>/editar/", views.UsuarioUpdateView.as_view(), name="usuarios_update"),
    path("<int:pk>/excluir/", views.UsuarioDeleteView.as_view(), name="usuarios_delete"),
    # CRUD de setores.
    path("setores/", views.GrupoListView.as_view(), name="setores_list"),
    path("setores/novo/", views.GrupoCreateView.as_view(), name="setores_create"),
    path("setores/<int:pk>/editar/", views.GrupoUpdateView.as_view(), name="setores_update"),
    path("setores/<int:pk>/excluir/", views.GrupoDeleteView.as_view(), name="setores_delete"),
    path("setores/auditoria-permissoes/", views.PermissionAuditListView.as_view(), name="setores_permissions_audit"),
    # Compatibilidade com URLs legadas.
    path("grupos/", RedirectView.as_view(pattern_name="setores_list", permanent=False)),
    path("grupos/novo/", RedirectView.as_view(pattern_name="setores_create", permanent=False)),
    path("grupos/<int:pk>/editar/", RedirectView.as_view(pattern_name="setores_update", permanent=False)),
    path("grupos/<int:pk>/excluir/", RedirectView.as_view(pattern_name="setores_delete", permanent=False)),
]
