"""Rotas do painel de rastreamento de navegacao."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.NavigationAnalyticsDashboardView.as_view(), name="rastreamento_navegacao_dashboard"),
    path(
        "paginas/<slug:page_token>/",
        views.NavigationAnalyticsDetailView.as_view(),
        name="rastreamento_navegacao_detail",
    ),
]
