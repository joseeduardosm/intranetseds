from django.urls import path

from . import views


urlpatterns = [
    path("auth/login/", views.desktop_login, name="desktop_api_login"),
    path("auth/logout/", views.desktop_logout, name="desktop_api_logout"),
    path("notificacoes/", views.desktop_notificacoes_list, name="desktop_api_notificacoes_list"),
    path(
        "notificacoes/<int:pk>/marcar-lida/",
        views.desktop_notificacao_marcar_lida,
        name="desktop_api_notificacao_marcar_lida",
    ),
    path(
        "notificacoes/<int:pk>/marcar-exibida/",
        views.desktop_notificacao_marcar_exibida,
        name="desktop_api_notificacao_marcar_exibida",
    ),
]

