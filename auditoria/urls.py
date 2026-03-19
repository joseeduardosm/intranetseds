"""
Roteamento HTTP do app `auditoria`.

Define as rotas públicas do módulo e conecta a URL base à view de
consulta de logs (`AuditLogListView`), que concentra filtros e regras
de autorização da trilha de auditoria.
"""

from django.urls import path

from .views import AuditLogListView

urlpatterns = [
    # Endpoint principal da trilha de auditoria.
    path("", AuditLogListView.as_view(), name="audit_log_list"),
]
